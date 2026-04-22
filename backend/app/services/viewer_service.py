"""Orchestrates ViewerProvider selection for a single document.

Thin layer: authorize via ``DocumentService.get``, pick a provider
by MIME, delegate. Lives as its own service so the HTTP handler
stays a one-liner and future conversion-heavy providers (F105.b)
can depend on it without dragging DocumentService into them.
"""

from __future__ import annotations

from uuid import UUID

from app.adapters.protocols import BlobStorage
from app.adapters.viewers import ViewablePayload, ViewerRegistry
from app.models import Document, DocumentStatus, User
from app.services.document_service import DocumentService


class ViewerService:
    def __init__(
        self,
        *,
        documents: DocumentService,
        storage: BlobStorage,
        registry: ViewerRegistry,
    ) -> None:
        self._documents = documents
        self._storage = storage
        self._registry = registry

    async def render(self, document_id: UUID, *, actor: User) -> ViewablePayload:
        # DocumentService.get raises NotFound / Forbidden for us; no
        # additional authorization layer needed here.
        doc: Document = await self._documents.get(document_id, actor=actor)

        if doc.status is not DocumentStatus.READY:
            # Per the plan-review decision: we don't 409 on a not-ready
            # doc because ``GET /documents/{id}`` returns 200 in the
            # same situation. Returning ``unsupported`` with a reason
            # keeps the frontend dispatch uniform — the "processing"
            # placeholder slots into the same switch as the real
            # "no viewer" case.
            return ViewablePayload(
                kind="unsupported",
                meta={
                    "filename": doc.filename,
                    "mime_type": doc.mime_type,
                    "status": doc.status.value,
                    "reason": "not_ready",
                },
            )

        provider = self._registry.for_mime(doc.mime_type)
        return await provider.render(doc, self._storage)
