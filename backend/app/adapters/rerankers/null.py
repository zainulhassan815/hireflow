"""No-op reranker.

Returned by the registry when reranking is disabled
(``reranker_provider=none``) or when it's enabled but the model
fails to load. Retrieval still works — candidates just pass through
in their original (RRF) order.
"""

from __future__ import annotations

from app.adapters.protocols import RerankCandidate


class NullReranker:
    """Passthrough. Preserves the incoming candidate order."""

    @property
    def model_name(self) -> str:
        return "none"

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        top_n: int | None = None,
    ) -> list[RerankCandidate]:
        if top_n is None:
            return list(candidates)
        return list(candidates[:top_n])
