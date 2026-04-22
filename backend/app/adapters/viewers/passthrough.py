"""Passthrough providers for formats the browser renders natively.

PDFs render via `<iframe>`, images via `<img>`. In both cases the
browser does the work; the provider's only job is to hand back a
time-limited MinIO URL the browser can GET directly.
"""

from __future__ import annotations

from app.adapters.protocols import BlobStorage
from app.adapters.viewers.protocol import ViewablePayload
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
    async def render(self, doc: Document, storage: BlobStorage) -> ViewablePayload:
        url = await storage.presigned_url(doc.storage_key, _URL_TTL_SECONDS)
        return ViewablePayload(
            kind="pdf",
            url=url,
            meta={"size_bytes": doc.size_bytes},
        )

    def accepts(self, mime_type: str | None) -> bool:
        return mime_type == "application/pdf"


class PassthroughImageProvider:
    async def render(self, doc: Document, storage: BlobStorage) -> ViewablePayload:
        url = await storage.presigned_url(doc.storage_key, _URL_TTL_SECONDS)
        return ViewablePayload(
            kind="image",
            url=url,
            meta={"size_bytes": doc.size_bytes, "mime_type": doc.mime_type},
        )

    def accepts(self, mime_type: str | None) -> bool:
        return mime_type in _IMAGE_MIME_TYPES
