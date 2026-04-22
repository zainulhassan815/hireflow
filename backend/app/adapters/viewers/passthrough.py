"""Passthrough providers for formats the browser renders natively.

PDFs render via ``<iframe>``, images via ``<img>``. In both cases the
browser does the work; the provider's job is to hand back a time-
limited MinIO URL the browser can GET directly.

F105.b introduced the ``prepare`` hook. Passthroughs have nothing to
convert, so ``prepare`` just records the source ``storage_key`` as
the viewable key. Render still falls back to ``doc.storage_key`` if
``viewable_key`` is unset, so pre-F105.b rows continue to work.
"""

from __future__ import annotations

from app.adapters.protocols import BlobStorage
from app.adapters.viewers.protocol import (
    PreparationResult,
    StorageGetSync,
    StoragePutSync,
    ViewablePayload,
)
from app.models import Document

# Kept narrow on purpose. We trust ``doc.mime_type`` because the upload
# path (DocumentService.upload) already validates against
# ``ALLOWED_MIME_TYPES``. Gmail-ingested docs pass through the same
# service method.
_IMAGE_MIME_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/tiff",
        "image/webp",
        "image/gif",
    }
)

# Signed URLs are short-lived. One hour is more than enough for an
# iframe to load and the user to finish reading one document in a
# dialog. Reopening the dialog re-requests the payload.
_URL_TTL_SECONDS = 3600


class PassthroughPdfProvider:
    def accepts(self, mime_type: str | None) -> bool:
        return mime_type == "application/pdf"

    def prepare(
        self,
        doc: Document,
        *,
        storage_get: StorageGetSync,
        storage_put: StoragePutSync,
    ) -> PreparationResult:
        return PreparationResult(kind="pdf", key=doc.storage_key)

    async def render(self, doc: Document, storage: BlobStorage) -> ViewablePayload:
        key = doc.viewable_key or doc.storage_key
        url = await storage.presigned_url(key, _URL_TTL_SECONDS)
        return ViewablePayload(
            kind="pdf",
            url=url,
            meta={"size_bytes": doc.size_bytes},
        )


class PassthroughImageProvider:
    def accepts(self, mime_type: str | None) -> bool:
        return mime_type in _IMAGE_MIME_TYPES

    def prepare(
        self,
        doc: Document,
        *,
        storage_get: StorageGetSync,
        storage_put: StoragePutSync,
    ) -> PreparationResult:
        return PreparationResult(kind="image", key=doc.storage_key)

    async def render(self, doc: Document, storage: BlobStorage) -> ViewablePayload:
        key = doc.viewable_key or doc.storage_key
        url = await storage.presigned_url(key, _URL_TTL_SECONDS)
        return ViewablePayload(
            kind="image",
            url=url,
            meta={"size_bytes": doc.size_bytes, "mime_type": doc.mime_type},
        )
