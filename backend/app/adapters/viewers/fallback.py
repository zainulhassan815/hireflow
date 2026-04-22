"""Fallback provider — accepts anything no real provider handles.

Its only job is to tell the frontend "no inline render; offer a
download." The fallback must be the LAST entry in the registry's
provider list, since ``accepts()`` returns True unconditionally.
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


class FallbackProvider:
    def accepts(self, mime_type: str | None) -> bool:
        return True

    def prepare(
        self,
        doc: Document,
        *,
        storage_get: StorageGetSync,
        storage_put: StoragePutSync,
    ) -> PreparationResult:
        return PreparationResult(kind="unsupported", key=None)

    async def render(self, doc: Document, storage: BlobStorage) -> ViewablePayload:
        return ViewablePayload(
            kind="unsupported",
            meta={
                "mime_type": doc.mime_type,
                "filename": doc.filename,
                "reason": "no_viewer_for_mime",
            },
        )
