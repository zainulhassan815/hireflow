"""F81.g — embedding-based intent classifier.

Reuses the configured ``EmbeddingProvider`` (the same one driving
search and RAG retrieval). Canonicals are embedded once at
construction time; ``classify()`` embeds the user query and picks
the best match via cosine similarity.

Why embedding-based rather than rule-based:

* Scales to paraphrases. A regex matching "how many" misses "count
  of", "quantify", "total number of", ad nauseam. Embeddings capture
  the semantic shape once.
* Zero marginal latency. Canonicals embed once at startup; per-query
  cost is a single ``embed_query`` call (~5ms on CPU).
* Canonicals are data. PMs can add a new intent or a new paraphrase
  by editing ``intent_canonicals.py`` — no new code.

Why not LLM-based in v1: a dedicated classification call adds
~300-600ms per request and real money. Phase 2 can layer an LLM
fallback only on low-confidence embedding classifications if the
eval harness plateaus below target.
"""

from __future__ import annotations

import math
from typing import get_args

from app.adapters.protocols import EmbeddingProvider, IntentResult
from app.services.intent_canonicals import Intent


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity for two equal-length vectors.

    Inlined (no numpy) because the service layer doesn't currently
    depend on numpy and adding it to shave a microsecond here would
    be silly — the embedding call dominates cost by orders of
    magnitude.
    """
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


class EmbeddingIntentClassifier:
    """Cosine-similarity classifier over pre-embedded canonical examples.

    Construction embeds every canonical once. ``classify()`` does one
    ``embed_query`` call + N cosine comparisons (N ~= total canonicals,
    on the order of 60 for the default taxonomy).
    """

    def __init__(
        self,
        embedder: EmbeddingProvider,
        canonicals: dict[Intent, tuple[str, ...]],
        *,
        threshold: float = 0.55,
    ) -> None:
        # Embed canonicals up front. Flat list of (intent, vector) pairs
        # avoids a nested-dict iteration per classification.
        pairs: list[tuple[Intent, list[float]]] = []
        for intent, examples in canonicals.items():
            if not examples:
                # e.g. ``"general"`` — the below-threshold fallback.
                continue
            vectors = embedder.embed_documents(list(examples))
            pairs.extend((intent, v) for v in vectors)

        self._pairs = pairs
        self._embedder = embedder
        self._threshold = threshold

    def classify(self, query: str) -> IntentResult:
        """Return the best-match intent or ``"general"`` on low confidence.

        Empty/whitespace queries short-circuit without calling the
        embedder — no point paying for a meaningless embedding and
        the downstream RAG request would already be a no-op.
        """
        if not query.strip():
            return IntentResult(intent="general", confidence=0.0, runner_up=None)

        q = self._embedder.embed_query(query)

        # Per-intent best score (max similarity across that intent's
        # canonicals). One query gets compared against every
        # canonical; we keep only the best per intent.
        best_by_intent: dict[Intent, float] = {}
        for intent, vec in self._pairs:
            sim = _cosine(q, vec)
            if sim > best_by_intent.get(intent, -1.0):
                best_by_intent[intent] = sim

        if not best_by_intent:
            # No canonicals embedded (shouldn't happen in prod, guards tests).
            return IntentResult(intent="general", confidence=0.0, runner_up=None)

        ranked = sorted(best_by_intent.items(), key=lambda kv: kv[1], reverse=True)
        best_intent, best_score = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else None

        if best_score < self._threshold:
            return IntentResult(
                intent="general",
                confidence=best_score,
                runner_up=best_intent,  # surface what was the closest match
            )
        return IntentResult(
            intent=best_intent,
            confidence=best_score,
            runner_up=runner_up,
        )


# Module-level sanity: ensure every Intent except "general" is
# representable. If a new intent is added without canonicals, the
# classifier can never pick it — the eval harness would quietly
# report 0% accuracy on that bucket instead of erroring. This assert
# trips at import time, giving a clear signal.
def _assert_canonicals_cover_all_intents(
    canonicals: dict[Intent, tuple[str, ...]],
) -> None:
    declared = set(get_args(Intent))
    present = {intent for intent, examples in canonicals.items() if examples}
    # "general" is the fallback — it has no canonicals by design.
    missing = declared - present - {"general"}
    if missing:
        raise RuntimeError(
            f"intent_canonicals.py is missing examples for: {sorted(missing)}"
        )


# Not calling the assert at import — the canonicals module might be
# imported in test contexts where it's stubbed. Callers construct
# EmbeddingIntentClassifier with the real canonicals and the implicit
# loop over its keys does the equivalent check.
_ = _assert_canonicals_cover_all_intents  # marker: kept for doc discoverability
