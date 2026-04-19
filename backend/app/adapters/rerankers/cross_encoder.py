"""Local cross-encoder reranker via sentence-transformers.

Default model: ``BAAI/bge-reranker-base`` — strong, ~280MB, pairs
naturally with our bge-small embedder. Model-agnostic by design:
any HF cross-encoder with a compatible task head works.

Loads lazily on first ``rerank`` call, then caches for the process
lifetime. One instance per process is enough; ``registry`` caches
the singleton.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from app.adapters.protocols import RerankCandidate

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Reranker backed by ``sentence_transformers.CrossEncoder``.

    The cross-encoder attends over (query, doc) pairs together,
    producing a relevance score per pair. More accurate than
    bi-encoder cosine similarity (what the vector store uses) but
    slower — run it on a small candidate set only.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-base",
        *,
        device: str | None = None,
        max_length: int = 512,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._max_length = max_length
        self._model: CrossEncoder | None = None
        self._load_lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        top_n: int | None = None,
    ) -> list[RerankCandidate]:
        if not candidates:
            return []
        model = self._ensure_loaded()

        pairs = [(query, c.text or "") for c in candidates]
        scores = model.predict(
            pairs,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        # Pair candidates with fresh scores and sort desc.
        indexed = sorted(
            zip(candidates, scores.tolist(), strict=True),
            key=lambda row: row[1],
            reverse=True,
        )
        ordered = [c for c, _ in indexed]
        if top_n is not None:
            ordered = ordered[:top_n]
        return ordered

    def _ensure_loaded(self) -> CrossEncoder:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            logger.info("loading cross-encoder %s", self._model_name)
            from sentence_transformers import CrossEncoder

            model = CrossEncoder(
                self._model_name,
                device=self._device,
                max_length=self._max_length,
            )
            self._model = model
            logger.info(
                "loaded cross-encoder %s on device=%s",
                self._model_name,
                model.model.device if hasattr(model, "model") else "unknown",
            )
            return self._model
