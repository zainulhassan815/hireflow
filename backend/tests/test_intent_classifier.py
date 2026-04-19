"""F81.g — EmbeddingIntentClassifier unit tests.

Uses a fake ``EmbeddingProvider`` so tests are fast and deterministic
— real sentence-transformers model loading takes 10+ seconds and
would bog down the fast test path. A dedicated eval suite
(``tests/eval/test_intent_accuracy.py``) runs against the real
embedder for end-to-end accuracy numbers.
"""

from __future__ import annotations

import pytest

from app.adapters.protocols import IntentResult
from app.services.intent_canonicals import Intent
from app.services.intent_classifier import EmbeddingIntentClassifier, _cosine

# ---------------------------------------------------------------------------
# Fake embedder — deterministic, word-overlap-based similarity
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    return {tok.lower() for tok in text.split() if len(tok) > 2}


def _bag_of_words_vector(text: str, vocab: list[str]) -> list[float]:
    """Turn text into a binary vector over ``vocab``.

    Not a real embedding — good enough to make tests assert against
    overlap semantics (more shared significant words → higher cosine).
    """
    tokens = _tokenize(text)
    return [1.0 if word in tokens else 0.0 for word in vocab]


class _FakeEmbedder:
    """Embedder stand-in. Produces deterministic overlap-based vectors."""

    # A hand-curated vocabulary that covers the vocabulary of our
    # canonical examples. Overlap between query and canonical drives
    # cosine similarity. Stable enough to write assertions against.
    _VOCAB: list[str] = [
        "count",
        "how",
        "many",
        "number",
        "quantify",
        "total",
        "compare",
        "versus",
        "difference",
        "contrast",
        "between",
        "rank",
        "best",
        "strongest",
        "fit",
        "top",
        "order",
        "prioritize",
        "does",
        "has",
        "can",
        "yes",
        "good",
        "worked",
        "where",
        "which",
        "mentioned",
        "document",
        "file",
        "appear",
        "summarize",
        "tell",
        "about",
        "overview",
        "brief",
        "description",
        "chronological",
        "timeline",
        "sequence",
        "year",
        "when",
        "extract",
        "pull",
        "all",
        "emails",
        "phone",
        "get",
        "urls",
        "skills",
        "stack",
        "technologies",
        "languages",
        "frameworks",
        "tools",
        "list",
        "enumerate",
        "libraries",
        "apis",
        "databases",
        "alice",
        "bob",
        "kubernetes",
        "python",
        "react",
        "svelte",
        "experience",
        "candidates",
        "resume",
        "resumes",
        "project",
        "restaurant",
        "signup",
        "backend",
        "frontend",
        "senior",
        "role",
    ]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_bag_of_words_vector(t, self._VOCAB) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return _bag_of_words_vector(text, self._VOCAB)

    @property
    def model_name(self) -> str:
        return "fake-bow-embedder"

    @property
    def dimension(self) -> int:
        return len(self._VOCAB)

    @property
    def recommended_distance_threshold(self) -> float:
        return 0.5


# ---------------------------------------------------------------------------
# Canonicals — a compact subset to keep the test predictable
# ---------------------------------------------------------------------------


_TEST_CANONICALS: dict[Intent, tuple[str, ...]] = {
    "count": (
        "how many candidates have Kubernetes experience",
        "count of resumes mentioning Python",
        "number of senior engineers in the corpus",
    ),
    "comparison": (
        "compare Alice and Bob",
        "difference between these candidates",
        "contrast React and Svelte",
    ),
    "ranking": (
        "which candidate is best for a senior role",
        "rank resumes by relevance",
        "top backend engineers",
    ),
    "yes_no": (
        "does Alice have Kubernetes",
        "has Bob worked with Python",
    ),
    "skill_list": (
        "what skills does Alice have",
        "tech stack of the restaurant project",
    ),
    "general": (),
}


# ---------------------------------------------------------------------------
# Happy path — each intent classifiable from a nearby paraphrase
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("count how many resumes mention Python", "count"),
        ("compare Alice and Bob skills", "comparison"),
        ("which backend engineer ranks best", "ranking"),
        ("does Alice have Python experience", "yes_no"),
        ("what skills does Bob have", "skill_list"),
    ],
)
def test_classifier_returns_expected_intent(query: str, expected: Intent) -> None:
    classifier = EmbeddingIntentClassifier(
        _FakeEmbedder(), _TEST_CANONICALS, threshold=0.1
    )
    result = classifier.classify(query)
    assert result.intent == expected


# ---------------------------------------------------------------------------
# Low-confidence fallback
# ---------------------------------------------------------------------------


def test_below_threshold_falls_back_to_general() -> None:
    """A query with near-zero overlap with any canonical should land
    in ``general`` — the default prose answer shape. Runner-up is
    preserved for observability."""
    classifier = EmbeddingIntentClassifier(
        _FakeEmbedder(), _TEST_CANONICALS, threshold=0.9
    )
    result = classifier.classify("xylophone flugelhorn quibble")
    assert result.intent == "general"
    # Runner-up exposes what the classifier thought was closest,
    # even though confidence was too low to commit.
    assert result.runner_up is not None


# ---------------------------------------------------------------------------
# Empty / whitespace queries short-circuit without calling embedder
# ---------------------------------------------------------------------------


class _TrackingEmbedder(_FakeEmbedder):
    def __init__(self) -> None:
        self.query_calls: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return super().embed_query(text)


def test_empty_query_short_circuits_without_embedding_call() -> None:
    """The classifier MUST NOT call ``embed_query`` on an empty string
    — at best it wastes compute, at worst produces an undefined vector
    whose cosine similarity is garbage."""
    embedder = _TrackingEmbedder()
    classifier = EmbeddingIntentClassifier(embedder, _TEST_CANONICALS)
    embedder.query_calls.clear()  # wipe canonical-indexing calls

    for query in ["", "   ", "\t\n"]:
        result = classifier.classify(query)
        assert result.intent == "general"
        assert result.confidence == 0.0
        assert result.runner_up is None

    assert embedder.query_calls == []


# ---------------------------------------------------------------------------
# Embed-once — canonicals indexed at construction, not per classify call
# ---------------------------------------------------------------------------


class _CountingEmbedder(_FakeEmbedder):
    def __init__(self) -> None:
        self.doc_calls = 0
        self.query_calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.doc_calls += 1
        return super().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return super().embed_query(text)


def test_canonicals_embed_once_at_construction() -> None:
    """If the classifier re-embedded canonicals on every query, a busy
    service would hammer the embedder. This test locks in the
    embed-once contract — construction embeds, classify() doesn't
    touch canonicals."""
    embedder = _CountingEmbedder()
    classifier = EmbeddingIntentClassifier(embedder, _TEST_CANONICALS)

    # One ``embed_documents`` call per non-empty intent group.
    non_empty_intents = sum(1 for examples in _TEST_CANONICALS.values() if examples)
    assert embedder.doc_calls == non_empty_intents

    # Each classify() call adds exactly one query embedding.
    classifier.classify("how many resumes")
    classifier.classify("compare Alice and Bob")
    classifier.classify("rank backend engineers")

    assert embedder.query_calls == 3
    assert embedder.doc_calls == non_empty_intents  # unchanged


# ---------------------------------------------------------------------------
# Cosine helper — contract tests
# ---------------------------------------------------------------------------


def test_cosine_identity() -> None:
    v = [1.0, 2.0, 3.0]
    assert _cosine(v, v) == pytest.approx(1.0)


def test_cosine_orthogonal() -> None:
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_zero_vector_is_zero_not_nan() -> None:
    """A zero vector would divide by zero; the helper returns 0.0
    rather than NaN so downstream ``argmax`` stays well-defined."""
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert _cosine([1.0, 1.0], [0.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# IntentResult shape contract
# ---------------------------------------------------------------------------


def test_intent_result_is_frozen_dataclass() -> None:
    """IntentResult must be immutable so logged/stored snapshots
    can't drift after the fact."""
    from dataclasses import FrozenInstanceError

    r = IntentResult(intent="count", confidence=0.9, runner_up="list")
    with pytest.raises(FrozenInstanceError):
        r.intent = "comparison"  # type: ignore[misc]
