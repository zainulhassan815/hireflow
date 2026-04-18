"""Runtime embedding-provider factory.

Single point where ``settings.embedding_provider`` becomes a concrete
adapter. Same shape as ``vision/registry.py`` and
``classifiers/registry.py``.

Returns a process-wide singleton — the underlying model is heavy
(~80MB for bge-small) and slow to load (~1-3s); we don't want to pay
that on every call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.protocols import EmbeddingProvider

if TYPE_CHECKING:
    from app.core.config import Settings

_singleton: EmbeddingProvider | None = None


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Return the configured embedding provider, building it once per process.

    The model itself loads lazily on first ``embed_*`` call (see
    ``SentenceTransformerEmbedder``), so this function is cheap to call
    from FastAPI lifespan or Celery worker startup.
    """
    global _singleton
    if _singleton is not None:
        return _singleton

    name = settings.embedding_provider.lower()

    if name == "local":
        from app.adapters.embeddings.sentence_transformer import (
            SentenceTransformerEmbedder,
        )

        _singleton = SentenceTransformerEmbedder(
            model_name=settings.embedding_model,
        )
        return _singleton

    raise ValueError(
        f"Unknown embedding_provider {name!r}. Expected: local. "
        "Add a new adapter under app/adapters/embeddings/ to support more."
    )


def reset_embedding_provider() -> None:
    """Drop the cached singleton. Used by tests; do not call in production."""
    global _singleton
    _singleton = None
