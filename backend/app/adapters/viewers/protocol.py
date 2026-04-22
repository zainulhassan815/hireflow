"""ViewerProvider Protocol + canonical payload shape.

Five kinds, no more. Every provider normalises to one of these so the
frontend dispatch stays a ``switch(kind)`` that never grows. New
formats add providers, not kinds.

F105.b added the ``prepare`` hook: providers that need to pre-compute
a renderable asset (office → PDF conversion, spreadsheet → JSON,
markdown → HTML) do so once at ingest. ``render`` stays fast — it
signs a URL or emits inline data, never blocks on heavy work.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from app.adapters.protocols import BlobStorage, StoredBlob
from app.models import Document

ViewableKind = Literal["pdf", "image", "table", "text", "unsupported"]


@dataclass
class ViewablePayload:
    """What the frontend needs to render a document.

    - ``url`` is set for ``pdf`` / ``image`` kinds (signed MinIO URL,
      time-limited).
    - ``data`` is set for ``table`` / ``text`` kinds (inline JSON —
      spreadsheets, plain text, markdown — delivered in the response
      itself rather than a second fetch).
    - ``meta`` carries render hints: page counts, sheet names,
      ``reason`` strings for ``unsupported``, etc.
    """

    kind: ViewableKind
    url: str | None = None
    data: dict | None = None
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PreparationResult:
    """Descriptor of the canonical viewable asset a provider prepared.

    Persisted on the ``Document`` row (``viewable_kind`` + ``viewable_key``)
    so the render path is a fast MinIO signature + nothing else.

    - ``kind``: the canonical kind the frontend will see.
    - ``key``: MinIO storage key of the asset, or ``None`` for kinds
      that don't use a URL (``unsupported``).
    """

    kind: ViewableKind
    key: str | None


# Narrow function types passed to ``prepare`` — providers don't need the
# full ``BlobStorage`` surface (async ``put`` / ``get``, ``delete``),
# just sync read / write, so we pass the two methods directly. Matches
# the ``storage_get: Callable[[str], bytes]`` shape ``ExtractionService``
# already uses.
StorageGetSync = Callable[[str], bytes]
StoragePutSync = Callable[[str, bytes, str], StoredBlob]


@runtime_checkable
class ViewerProvider(Protocol):
    """Stateless adapter: declare a MIME class, prepare once, render fast.

    ``prepare`` runs inside the Celery worker's sync context after
    extraction completes — heavy work (LibreOffice subprocess, etc.)
    lives here. ``render`` runs inside a FastAPI request — stays
    async, never blocks on conversion.
    """

    def accepts(self, mime_type: str | None) -> bool: ...

    def prepare(
        self,
        doc: Document,
        *,
        storage_get: StorageGetSync,
        storage_put: StoragePutSync,
    ) -> PreparationResult: ...

    async def render(self, doc: Document, storage: BlobStorage) -> ViewablePayload: ...
