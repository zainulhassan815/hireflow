"""Text / markdown provider (F105.d).

Handles plain text and markdown. Source bytes are decoded UTF-8 with
replacement fallback (a rogue byte surfaces as the replacement char
rather than crashing the prep step). Output inlined directly in the
response — no MinIO round-trip for text, since the content IS the
viewable payload.

Scope is deliberately narrow: text/plain, text/markdown,
application/x-log. CSV / TSV are handled by F105.c's ``CsvTsvProvider``
(table UX beats raw text). DOCX / ODT are handled by F105.b (PDF
render of the full formatted document). This is the "unformatted
body of characters" provider.
"""

from __future__ import annotations

import logging

from app.adapters.protocols import BlobStorage
from app.adapters.viewers.protocol import (
    PreparationResult,
    StorageGetSync,
    StoragePutSync,
    ViewablePayload,
)
from app.models import Document

logger = logging.getLogger(__name__)

# 5 MB cap. Inline text payloads past this size bloat the JSON
# response and make the browser scroll lag. Oversized docs fall
# through to ``unsupported`` + download affordance.
_MAX_INLINE_BYTES = 5 * 1024 * 1024

_PLAIN_MIMES = frozenset(
    {
        "text/plain",
        "application/x-log",
    }
)
_MARKDOWN_MIMES = frozenset(
    {
        "text/markdown",
        "text/x-markdown",
    }
)


class TextProvider:
    def accepts(self, mime_type: str | None) -> bool:
        return mime_type in _PLAIN_MIMES or mime_type in _MARKDOWN_MIMES

    def prepare(
        self,
        doc: Document,
        *,
        storage_get: StorageGetSync,
        storage_put: StoragePutSync,
    ) -> PreparationResult:
        # Nothing to convert — source bytes are already human-readable.
        # Record the source storage_key as the viewable key so ``render``
        # knows prep has run (viewable_key IS NULL triggers the
        # conversion-pending sentinel on other providers).
        return PreparationResult(kind="text", key=doc.storage_key)

    async def render(self, doc: Document, storage: BlobStorage) -> ViewablePayload:
        if doc.size_bytes > _MAX_INLINE_BYTES:
            return ViewablePayload(
                kind="unsupported",
                meta={
                    "filename": doc.filename,
                    "mime_type": doc.mime_type,
                    "reason": "too_large_to_inline",
                    "size_bytes": doc.size_bytes,
                    "limit_bytes": _MAX_INLINE_BYTES,
                },
            )

        key = doc.viewable_key or doc.storage_key
        blob = await storage.get(key)
        content = blob.decode("utf-8", errors="replace")
        fmt = "markdown" if doc.mime_type in _MARKDOWN_MIMES else "plain"
        logger.info(
            "text render: filename=%s format=%s bytes=%d",
            doc.filename,
            fmt,
            len(blob),
        )
        return ViewablePayload(
            kind="text",
            data={"content": content, "format": fmt},
            meta={"filename": doc.filename},
        )
