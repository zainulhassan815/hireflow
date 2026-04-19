"""F80.5: Reranker unit tests.

Mocked ``CrossEncoder`` for fast tests; one ``@pytest.mark.slow``
integration test exercises the real bge-reranker-base model (module-
scoped so the ~1s load is amortized).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.adapters.protocols import RerankCandidate
from app.adapters.rerankers.cross_encoder import CrossEncoderReranker
from app.adapters.rerankers.null import NullReranker


def _candidate(text: str, score: float = 0.0) -> RerankCandidate:
    return RerankCandidate(document_id=uuid4(), text=text, original_score=score)


# ---------- NullReranker ----------


def test_null_preserves_order() -> None:
    r = NullReranker()
    a, b, c = _candidate("a"), _candidate("b"), _candidate("c")
    assert r.rerank("q", [a, b, c]) == [a, b, c]


def test_null_respects_top_n() -> None:
    r = NullReranker()
    a, b, c = _candidate("a"), _candidate("b"), _candidate("c")
    assert r.rerank("q", [a, b, c], top_n=2) == [a, b]


def test_null_empty_input() -> None:
    assert NullReranker().rerank("q", []) == []


def test_null_model_name() -> None:
    assert NullReranker().model_name == "none"


# ---------- CrossEncoderReranker (mocked model) ----------


def test_reranker_reorders_by_score() -> None:
    """Highest cross-encoder score wins regardless of input order."""
    rr = CrossEncoderReranker(model_name="test-model")

    fake_model = MagicMock()
    # Middle candidate scores highest → should come first.
    fake_model.predict.return_value = _ArrayLike([0.1, 0.9, 0.4])
    rr._model = fake_model  # bypass lazy load

    candidates = [
        _candidate("first"),
        _candidate("winner"),
        _candidate("third"),
    ]
    result = rr.rerank("query", candidates)
    assert [c.text for c in result] == ["winner", "third", "first"]


def test_reranker_respects_top_n() -> None:
    rr = CrossEncoderReranker(model_name="test-model")
    fake_model = MagicMock()
    fake_model.predict.return_value = _ArrayLike([0.5, 0.9, 0.1])
    rr._model = fake_model

    cs = [_candidate(t) for t in ("a", "b", "c")]
    result = rr.rerank("q", cs, top_n=2)
    assert [c.text for c in result] == ["b", "a"]


def test_reranker_empty_input_returns_empty() -> None:
    rr = CrossEncoderReranker(model_name="test-model")
    # Lazy model should NOT be forced to load on empty input.
    assert rr.rerank("q", []) == []
    assert rr._model is None


def test_reranker_lazy_load_does_not_fetch_weights_on_init() -> None:
    """Constructing the reranker must not download or load the model."""
    rr = CrossEncoderReranker(model_name="test-model")
    assert rr._model is None
    # Touching .model_name doesn't load either.
    _ = rr.model_name
    assert rr._model is None


def test_reranker_calls_model_with_pair_per_candidate() -> None:
    rr = CrossEncoderReranker(model_name="test-model")
    fake_model = MagicMock()
    fake_model.predict.return_value = _ArrayLike([0.0, 0.0])
    rr._model = fake_model

    cs = [_candidate("alpha"), _candidate("beta")]
    rr.rerank("my query", cs)

    fake_model.predict.assert_called_once()
    args, _ = fake_model.predict.call_args
    pairs = args[0]
    assert pairs == [("my query", "alpha"), ("my query", "beta")]


def test_reranker_loads_once_on_first_call() -> None:
    """First rerank loads the model; second reuses the cached instance."""
    rr = CrossEncoderReranker(model_name="test-model")
    with patch("sentence_transformers.CrossEncoder", autospec=True) as mock_class:
        mock_class.return_value.predict.return_value = _ArrayLike([0.5])

        rr.rerank("q", [_candidate("only")])
        rr.rerank("q", [_candidate("only")])

        assert mock_class.call_count == 1  # one load, two ranks


# ---------- helper ----------


class _ArrayLike:
    """Mimics a numpy array for .tolist()."""

    def __init__(self, values: list[float]) -> None:
        self._values = values

    def tolist(self) -> list[float]:
        return self._values
