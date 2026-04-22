"""ViewerProvider Protocol + canonical payload shape.

Five kinds, no more. Every provider normalises to one of these so the
frontend dispatch stays a ``switch(kind)`` that never grows. New
formats add providers, not kinds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from app.adapters.protocols import BlobStorage
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


@runtime_checkable
class ViewerProvider(Protocol):
    """Stateless adapter: declare a MIME class + produce a payload.

    ``render`` is async to give future providers room to call
    conversion tools (LibreOffice, pandoc) without breaking the
    Protocol signature. Passthrough providers that only sign a URL
    still fit — they just don't await heavy work.
    """

    def accepts(self, mime_type: str | None) -> bool: ...

    async def render(self, doc: Document, storage: BlobStorage) -> ViewablePayload: ...
