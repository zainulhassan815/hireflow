"""F81.g — intent-classification accuracy eval against the real embedder.

Runs on a labeled set of ~60 queries. Reports per-intent accuracy
and dumps misclassifications for triage. Fails if overall accuracy
drops below ``INTENT_ACCURACY_THRESHOLD``.

Ownership: the canonicals live in
``app/services/intent_canonicals.py``; the labeled queries live next
to this file in ``intent_queries.json``. Both are data — when the
eval flags misclassifications, the fix is usually to add a
paraphrase to the canonicals or, less often, to the labels.

Run with ``make eval-intent``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

# Start low; raise when we have more labeled data. 80% on the
# current fixture is hard-coded as the reviewable gate.
INTENT_ACCURACY_THRESHOLD = 0.80


@pytest.fixture(scope="session")
def intent_classifier():
    """Build the real ``EmbeddingIntentClassifier`` once per session.

    Imports the canonicals + the configured embedding provider via
    the same factory the runtime uses. Slow on first call (embedder
    model loads + ~60 canonicals embed) — session scope keeps the
    second run fast for iterative tuning.
    """
    from app.adapters.embeddings.registry import get_embedding_provider
    from app.core.config import settings
    from app.services.intent_canonicals import CANONICALS
    from app.services.intent_classifier import EmbeddingIntentClassifier

    embedder = get_embedding_provider(settings)
    return EmbeddingIntentClassifier(embedder, CANONICALS)


def _load_cases() -> list[dict]:
    path = Path(__file__).parent / "intent_queries.json"
    with path.open() as f:
        cases = json.load(f)
    assert isinstance(cases, list) and cases
    return cases


def test_intent_classification_accuracy(intent_classifier, capsys) -> None:
    cases = _load_cases()

    per_intent: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [correct, total]
    misses: list[dict] = []

    for case in cases:
        expected = case["intent"]
        result = intent_classifier.classify(case["query"])
        per_intent[expected][1] += 1
        if result.intent == expected:
            per_intent[expected][0] += 1
        else:
            misses.append(
                {
                    "query": case["query"],
                    "expected": expected,
                    "got": result.intent,
                    "confidence": result.confidence,
                    "runner_up": result.runner_up,
                }
            )

    total = sum(total for _, total in per_intent.values())
    correct = sum(c for c, _ in per_intent.values())
    overall = correct / total if total else 0.0

    # Print the per-intent scorecard even when the test passes —
    # the operator running ``make eval-intent`` wants to see the
    # breakdown, not just a green dot.
    with capsys.disabled():
        print("\nIntent classification eval")
        print(f"  overall: {overall:.1%} ({correct}/{total})")
        for intent, (c, t) in sorted(per_intent.items()):
            pct = c / t if t else 0.0
            bar = "#" * int(pct * 14) + "." * (14 - int(pct * 14))
            print(f"  {intent:<12} {bar} {pct:>5.0%}  ({c}/{t})")
        if misses:
            print(f"\n  {len(misses)} misclassifications:")
            for m in misses[:15]:
                print(
                    f"    [{m['expected']:<10} -> {m['got']:<10} "
                    f"@ {m['confidence']:.2f}"
                    f"{'  runner=' + m['runner_up'] if m['runner_up'] else ''}] "
                    f"{m['query']}"
                )
            if len(misses) > 15:
                print(f"    ... and {len(misses) - 15} more")

    assert overall >= INTENT_ACCURACY_THRESHOLD, (
        f"Intent accuracy {overall:.1%} below threshold "
        f"{INTENT_ACCURACY_THRESHOLD:.1%}. Review misclassifications "
        f"above and either add paraphrases to intent_canonicals.py or "
        f"fix the labels in intent_queries.json."
    )
