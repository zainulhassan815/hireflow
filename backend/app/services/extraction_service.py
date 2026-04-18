"""Document processing pipeline.

Called by a Celery task, not by a FastAPI route. Runs synchronously inside
the worker process. Uses its own DB session (not request-scoped).

Pipeline: fetch blob → extract text → classify → index embeddings → commit.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.adapters.protocols import (
    ChunkContextualizer,
    DocumentClassifier,
    Element,
    TextExtractor,
)
from app.models import Document, DocumentElement, DocumentStatus, DocumentType
from app.services.chunking import CHUNKING_VERSION, chunk_elements
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


# Bumped when the extractor or its output shape changes in a way that
# invalidates stored element rows. Stamped on each doc at process time.
EXTRACTION_VERSION = "v2-unstructured"


class ExtractionService:
    def __init__(
        self,
        session: Session,
        extractor: TextExtractor,
        classifier: DocumentClassifier,
        storage_get: Callable[[str], bytes],
        embedding: EmbeddingService | None = None,
        contextualizer: ChunkContextualizer | None = None,
        on_ready: Callable[[Document], None] | None = None,
    ) -> None:
        self._session = session
        self._extractor = extractor
        self._classifier = classifier
        self._storage_get = storage_get
        self._embedding = embedding
        self._contextualizer = contextualizer
        self._on_ready = on_ready

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
            self._index(doc)
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

        # Ready-side hook fires after commit so downstream consumers
        # (auto-candidate creation, notifications, etc.) see the final
        # persisted state. Never runs on failure.
        if doc.status == DocumentStatus.READY and self._on_ready is not None:
            self._on_ready(doc)

    def _extract(self, doc: Document) -> None:
        data = self._storage_get(doc.storage_key)
        result = self._extractor.extract(data, doc.mime_type)
        doc.extracted_text = result.text
        doc.extraction_version = EXTRACTION_VERSION
        if result.page_count is not None:
            doc.metadata_ = {**(doc.metadata_ or {}), "page_count": result.page_count}
        self._persist_elements(doc, result.elements)

    def _persist_elements(self, doc: Document, elements: list[Element]) -> None:
        """Replace any prior elements with the fresh extraction output.

        Delete-then-insert is simpler than a merge and, on re-extraction,
        the element set can change wholesale. CASCADE on the FK handles
        cleanup if the parent doc is ever deleted.
        """
        self._session.execute(
            delete(DocumentElement).where(DocumentElement.document_id == doc.id)
        )
        for element in elements:
            self._session.add(
                DocumentElement(
                    document_id=doc.id,
                    kind=element.kind,
                    text=element.text,
                    page_number=element.page_number,
                    order_index=element.order,
                    metadata_=element.metadata or None,
                )
            )

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

    def _index(self, doc: Document) -> None:
        if self._embedding is None:
            return
        try:
            # Pass the fresh element objects rather than reloading them
            # from the session — we haven't committed yet and eager-
            # loading would round-trip unnecessarily.
            elements = [
                Element(
                    kind=row.kind,
                    text=row.text,
                    page_number=row.page_number,
                    order=row.order_index,
                    metadata=row.metadata_ or {},
                )
                for row in sorted(doc.elements, key=lambda r: r.order_index)
            ]
            chunks = chunk_elements(elements)
            if self._contextualizer is not None:
                chunks = self._contextualizer.contextualize(doc, chunks)
            self._embedding.index_document(doc, chunks=chunks)
            doc.chunking_version = CHUNKING_VERSION
        except Exception:
            # Indexing failure is non-fatal — the document is still usable
            # without search. Log and continue so status reaches READY.
            logger.exception("embedding indexing failed for document %s", doc.id)
