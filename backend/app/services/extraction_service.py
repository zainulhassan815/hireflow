"""Document text-extraction and classification orchestration.

Called by a Celery task, not by a FastAPI route. Runs synchronously inside
the worker process. Uses its own DB session (not request-scoped).

Pipeline: fetch blob → extract text → classify → extract metadata → commit.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.protocols import DocumentClassifier, TextExtractor
from app.models import Document, DocumentStatus, DocumentType

logger = logging.getLogger(__name__)


class ExtractionService:
    def __init__(
        self,
        session: Session,
        extractor: TextExtractor,
        classifier: DocumentClassifier,
        storage_get: Callable[[str], bytes],
    ) -> None:
        self._session = session
        self._extractor = extractor
        self._classifier = classifier
        self._storage_get = storage_get

    def process(self, document_id: UUID) -> None:
        doc = self._session.execute(
            select(Document).where(Document.id == document_id)
        ).scalar_one_or_none()

        if doc is None:
            logger.warning("document %s not found, skipping", document_id)
            return

        if doc.status != DocumentStatus.PENDING:
            logger.info("document %s status is %s, skipping", document_id, doc.status)
            return

        doc.status = DocumentStatus.PROCESSING
        self._session.commit()

        try:
            self._extract(doc)
            self._classify(doc)
            doc.status = DocumentStatus.READY
            logger.info(
                "document %s processed: type=%s, %d chars",
                document_id,
                doc.document_type,
                len(doc.extracted_text or ""),
            )
        except Exception:
            doc.status = DocumentStatus.FAILED
            logger.exception("processing failed for document %s", document_id)

        self._session.commit()

    def _extract(self, doc: Document) -> None:
        data = self._storage_get(doc.storage_key)
        result = self._extractor.extract(data, doc.mime_type)
        doc.extracted_text = result.text
        if result.page_count is not None:
            doc.metadata_ = {**(doc.metadata_ or {}), "page_count": result.page_count}

    def _classify(self, doc: Document) -> None:
        text = doc.extracted_text
        if not text or not text.strip():
            logger.info("document %s has no text, skipping classification", doc.id)
            return

        result = self._classifier.classify(text, doc.filename)

        valid_types = {t.value for t in DocumentType}
        if result.document_type in valid_types:
            doc.document_type = DocumentType(result.document_type)

        existing = doc.metadata_ or {}
        merged = {
            **existing,
            **result.metadata,
            "classification_confidence": result.confidence,
        }
        doc.metadata_ = merged
