"""Document text-extraction orchestration.

Called by a Celery task, not by a FastAPI route. Runs synchronously inside
the worker process. Uses its own DB session (not request-scoped).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.protocols import TextExtractor
from app.models import Document, DocumentStatus

logger = logging.getLogger(__name__)


class ExtractionService:
    def __init__(
        self,
        session: Session,
        extractor: TextExtractor,
        storage_get: Callable[[str], bytes],
    ) -> None:
        self._session = session
        self._extractor = extractor
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
            data = self._storage_get(doc.storage_key)
            result = self._extractor.extract(data, doc.mime_type)
            doc.extracted_text = result.text
            doc.status = DocumentStatus.READY
            if result.page_count is not None:
                doc.metadata_ = {
                    **(doc.metadata_ or {}),
                    "page_count": result.page_count,
                }
            logger.info(
                "document %s extracted (%d chars)", document_id, len(result.text)
            )
        except Exception:
            doc.status = DocumentStatus.FAILED
            logger.exception("extraction failed for document %s", document_id)

        self._session.commit()
