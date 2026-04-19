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


# F85.d: per-model cosine-distance cutoffs. Derived from probing each
# model on our eval corpus — relevant hits cluster well below the
# threshold, irrelevant hits sit above it. Add new models as you A/B
# them (F85.b). Unknown models fall through to _DEFAULT_THRESHOLD
# with a one-off warning.
_MODEL_DISTANCE_THRESHOLDS: dict[str, float] = {
    # BGE family — normalized embeddings, tight distribution.
    "BAAI/bge-small-en-v1.5": 0.35,
    "BAAI/bge-base-en-v1.5": 0.35,
    "BAAI/bge-large-en-v1.5": 0.35,
    # all-MiniLM family — wider distribution, Chroma's historical default.
    "sentence-transformers/all-MiniLM-L6-v2": 0.60,
    "sentence-transformers/all-MiniLM-L12-v2": 0.60,
    "sentence-transformers/all-mpnet-base-v2": 0.60,
    # e5 family — instruct-tuned; tighter when used with query: / passage:
    # prefixes, looser without them. Values here assume raw use (no
    # prefixes) until F85.e ships.
    "intfloat/e5-small-v2": 0.50,
    "intfloat/e5-base-v2": 0.50,
    "intfloat/e5-large-v2": 0.50,
    # Nomic — larger embedding space, needs its own calibration run.
    "nomic-ai/nomic-embed-text-v1.5": 0.45,
    # Jina v2 — similar profile to BGE.
    "jinaai/jina-embeddings-v2-base-en": 0.40,
}

_DEFAULT_THRESHOLD = 0.5


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

    @property
    def recommended_distance_threshold(self) -> float:
        """Per-model cosine-distance cutoff. F85.d.

        Falls back to ``_DEFAULT_THRESHOLD`` with a one-off warning
        when the configured model isn't in the curated table. If you
        just added a new model to ``EMBEDDING_MODEL`` and get the
        fallback warning, probe it on a small corpus and add an entry
        above.
        """
        threshold = _MODEL_DISTANCE_THRESHOLDS.get(self._model_name)
        if threshold is None:
            if not getattr(self, "_warned_no_threshold", False):
                logger.warning(
                    "no curated distance threshold for model %r — using "
                    "default %.2f. Add an entry to "
                    "_MODEL_DISTANCE_THRESHOLDS after A/B-ing eval.",
                    self._model_name,
                    _DEFAULT_THRESHOLD,
                )
                self._warned_no_threshold = True
            return _DEFAULT_THRESHOLD
        return threshold

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
            getter = (
                getattr(model, "get_embedding_dimension", None)
                or model.get_sentence_embedding_dimension
            )
            self._dimension = int(getter())
            self._model = model
            logger.info(
                "loaded %s (dim=%d, device=%s)",
                self._model_name,
                self._dimension,
                model.device,
            )
            return self._model
