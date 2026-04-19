"""F89.c — mean-pool helper unit tests.

Pure-function coverage: empty input, dimension mismatch, orthogonal
vectors, identical vectors, zero-vector edge case. No Chroma, no
embedder — the helper only operates on lists of floats.
"""

from __future__ import annotations

import math

import pytest

from app.services.document_vector import pool_document_embedding


def _l2(vec: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vec))


def test_empty_input_raises() -> None:
    with pytest.raises(ValueError, match="empty list"):
        pool_document_embedding([])


def test_zero_dimension_raises() -> None:
    with pytest.raises(ValueError, match="non-zero dimension"):
        pool_document_embedding([[]])


def test_ragged_input_raises() -> None:
    with pytest.raises(ValueError, match="dimension mismatch"):
        pool_document_embedding([[1.0, 0.0], [1.0, 0.0, 0.0]])


def test_single_vector_is_renormalized_to_unit() -> None:
    """One chunk → pooled vector is that chunk renormalized. If the
    input was already unit, we get the same vector back (modulo fp)."""
    unit = [1.0, 0.0, 0.0]
    pooled = pool_document_embedding([unit])
    assert pytest.approx(_l2(pooled), abs=1e-9) == 1.0
    assert pooled == pytest.approx(unit, abs=1e-9)


def test_identical_vectors_pool_to_themselves() -> None:
    """Two copies of the same unit vector mean-pool to that vector."""
    v = [0.6, 0.8, 0.0]
    pooled = pool_document_embedding([v, v, v])
    assert pytest.approx(_l2(pooled), abs=1e-9) == 1.0
    assert pooled == pytest.approx(v, abs=1e-9)


def test_orthogonal_vectors_pool_to_normalized_mean() -> None:
    """Two orthogonal unit vectors mean to (0.5, 0.5, 0) then
    renormalize to 1/sqrt(2) on each of the first two axes."""
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    pooled = pool_document_embedding([a, b])
    expected = [1 / math.sqrt(2), 1 / math.sqrt(2), 0.0]
    assert pooled == pytest.approx(expected, abs=1e-9)
    assert pytest.approx(_l2(pooled), abs=1e-9) == 1.0


def test_zero_sum_raises() -> None:
    """Two antipodal unit vectors mean to the zero vector; can't
    renormalize. Must raise rather than return NaNs or a zero vector
    silently — downstream cosine similarity would be meaningless."""
    with pytest.raises(ValueError, match="zero norm"):
        pool_document_embedding([[1.0, 0.0], [-1.0, 0.0]])


def test_dominated_by_repeated_chunk() -> None:
    """Mean-pool is susceptible to chunk repetition — same axis
    repeated many times pulls the centroid toward it. Documents that
    behaviour so the caller knows it when ranking is coarse."""
    dominant = [1.0, 0.0, 0.0]
    minority = [0.0, 1.0, 0.0]
    pooled = pool_document_embedding([dominant, dominant, dominant, minority])
    # First axis component after normalization should be much larger
    # than the second axis.
    assert pooled[0] > pooled[1]
    assert pytest.approx(_l2(pooled), abs=1e-9) == 1.0
