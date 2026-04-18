"""Local embedding provider backed by sentence-transformers.

Loads any model from the HuggingFace hub by name. Default is
``BAAI/bge-small-en-v1.5`` — same vector size as Chroma's bundled
all-MiniLM-L6-v2 (384) but consistently better on the MTEB English
retrieval benchmark.

The model is loaded lazily on the first ``embed_*`` call, then cached
for the lifetime of the instance. One instance per process is enough;
the registry/DI wires the singleton.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class SentenceTransformerEmbedder:
    """``EmbeddingProvider`` implementation using sentence-transformers.

    Thread-safe lazy load. The first call to ``embed_documents`` /
    ``embed_query`` materialises the model; subsequent calls reuse it.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        *,
        device: str | None = None,
        normalize_embeddings: bool = True,
    ) -> None:
        self._model_name = model_name
        self._device = device  # None → auto-pick (cuda > mps > cpu)
        self._normalize = normalize_embeddings
        self._model: SentenceTransformer | None = None
        self._dimension: int | None = None
        self._load_lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        # First call triggers load; subsequent calls hit the cached value.
        self._ensure_loaded()
        assert self._dimension is not None
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure_loaded()
        vectors = model.encode(
            texts,
            normalize_embeddings=self._normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        # No query/document asymmetry for bge-small-v1.5 — same model
        # call. If a future model needs a "query: " prefix we'd add it
        # here without changing callers.
        model = self._ensure_loaded()
        vector = model.encode(
            text,
            normalize_embeddings=self._normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vector.tolist()

    def _ensure_loaded(self) -> SentenceTransformer:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            logger.info("loading sentence-transformer model %s", self._model_name)
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(self._model_name, device=self._device)
            # sentence-transformers renamed this method in a recent
            # release; fall back if we're on the old API.
            getter = getattr(
                model, "get_embedding_dimension", None
            ) or model.get_sentence_embedding_dimension
            self._dimension = int(getter())
            self._model = model
            logger.info(
                "loaded %s (dim=%d, device=%s)",
                self._model_name,
                self._dimension,
                model.device,
            )
            return self._model
