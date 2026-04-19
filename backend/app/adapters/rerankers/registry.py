"""Reranker factory + process-wide singleton.

Cross-encoder models are heavy (~280MB weights for bge-reranker-base)
and slow to load (~1-3s). Build once per process, cache.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.adapters.protocols import Reranker

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_singleton: Reranker | None = None


def get_reranker(settings: Settings) -> Reranker:
    """Return the configured reranker, building once per process.

    Disabled (``reranker_provider=none``) returns a ``NullReranker`` —
    the rest of the pipeline still calls ``.rerank`` but candidates
    pass through unchanged.
    """
    global _singleton
    if _singleton is not None:
        return _singleton

    name = settings.reranker_provider.lower()

    if name == "none":
        from app.adapters.rerankers.null import NullReranker

        _singleton = NullReranker()
        return _singleton

    if name == "local":
        from app.adapters.rerankers.cross_encoder import CrossEncoderReranker

        _singleton = CrossEncoderReranker(model_name=settings.reranker_model)
        return _singleton

    raise ValueError(f"Unknown reranker_provider {name!r}. Expected: local, none.")


def reset_reranker() -> None:
    """Drop the cached singleton. Test-only."""
    global _singleton
    _singleton = None
