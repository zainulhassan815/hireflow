"""F105.b — run viewer prep after a document finishes extraction.

Called from the Celery worker after ``ExtractionService.process``
commits a document as READY. Picks the matching ``ViewerProvider``,
runs ``prepare`` (which may shell out to LibreOffice), and writes
``viewable_kind`` + ``viewable_key`` on the document row.

Failures never propagate out — a prep error must not reverse the
document's READY state or trigger Celery's retry loop (retries are
for transient extraction failures, not viewable-asset hiccups). A
failed prep leaves the viewable columns NULL; the render path then
returns ``kind="unsupported"`` with a reason string so the user
sees a download affordance.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.viewers import LibreOfficeUnavailable, ViewerRegistry
from app.adapters.viewers.protocol import StorageGetSync, StoragePutSync
from app.models import Document

logger = logging.getLogger(__name__)


class ViewerPreparationService:
    def __init__(
        self,
        *,
        session: Session,
        registry: ViewerRegistry,
        storage_get: StorageGetSync,
        storage_put: StoragePutSync,
    ) -> None:
        self._session = session
        self._registry = registry
        self._storage_get = storage_get
        self._storage_put = storage_put

    def prepare(self, document_id: UUID) -> None:
        doc = self._session.execute(
            select(Document).where(Document.id == document_id)
        ).scalar_one_or_none()

        if doc is None:
            logger.info("viewer prep: document %s not found, skipping", document_id)
            return

        try:
            provider = self._registry.for_mime(doc.mime_type)
            result = provider.prepare(
                doc,
                storage_get=self._storage_get,
                storage_put=self._storage_put,
            )
        except LibreOfficeUnavailable:
            # Dev-mode or worker-image mis-build. Don't spam ERROR — the
            # pipeline is functional; the user just sees a download
            # fallback for office files.
            logger.warning(
                "viewer prep: libreoffice not available; doc %s stays viewer-less",
                document_id,
            )
            return
        except Exception:
            logger.warning(
                "viewer prep failed for document %s", document_id, exc_info=True
            )
            return

        doc.viewable_kind = result.kind
        doc.viewable_key = result.key
        self._session.commit()
        logger.info(
            "viewer prep: doc %s kind=%s key=%s",
            document_id,
            result.kind,
            result.key,
        )
