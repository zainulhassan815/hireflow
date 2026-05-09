"""No-op contextualizer.

Returned by the registry when contextualization is disabled
(``contextualizer_provider=none``) or when it's enabled but no
``LlmProvider`` is configured. The pipeline keeps working — chunks
just don't gain context, which is strictly worse for retrieval but
not a failure mode.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Document
    from app.services.chunking import Chunk


# F103.d — distinct stamp value so callers can tell "never
# contextualized" (this) apart from "contextualized with v1/v2 prompt".
_NULL_CONTEXTUALIZATION_VERSION = "null"


class NullChunkContextualizer:
    """No-op. Returns chunks unchanged but stamps the version key."""

    @property
    def model_name(self) -> str:
        return "none"

    def contextualize(self, document: Document, chunks: list[Chunk]) -> list[Chunk]:
        document.metadata_ = {
            **(document.metadata_ or {}),
            "contextualization_version": _NULL_CONTEXTUALIZATION_VERSION,
        }
        return chunks
