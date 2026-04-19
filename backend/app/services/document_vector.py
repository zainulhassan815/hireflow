"""Doc-level vector construction from chunk embeddings (F89.c).

Similarity search wants one vector per document. Re-embedding the full
text loses everything past the model's context window (bge-small caps
at 512 tokens — a typical résumé is already over that). Instead, pool
the already-computed chunk embeddings into a single unit vector.

Mean-pool + L2-renormalize yields a centroid pointing at the doc's
topic distribution in embedding space; after renormalization it lives
on the same unit sphere as the query vector, so cosine distance in the
Chroma doc-level collection is directly comparable across docs.

Pure function — no providers, no IO. Lives in ``services/`` because
it's domain logic over embedding vectors, not a swappable adapter.
"""

from __future__ import annotations

import math


def pool_document_embedding(chunk_embeddings: list[list[float]]) -> list[float]:
    """Mean-pool chunk vectors and L2-normalize the result.

    ``chunk_embeddings`` must be non-empty and every vector must be the
    same length — enforced here so callers can't silently feed in a
    ragged batch. Returns a new list of floats with L2 norm 1.0 (up to
    floating-point noise).

    Raises ``ValueError`` on empty input or mismatched dimensions. The
    embedding-pipeline callers already skip empty-chunk docs, so the
    empty case should never reach us in production; raising is defensive.
    """
    if not chunk_embeddings:
        raise ValueError("Cannot pool an empty list of chunk embeddings.")

    dim = len(chunk_embeddings[0])
    if dim == 0:
        raise ValueError("Chunk embeddings must have non-zero dimension.")

    summed = [0.0] * dim
    for vec in chunk_embeddings:
        if len(vec) != dim:
            raise ValueError(
                f"Chunk embedding dimension mismatch: expected {dim}, got {len(vec)}."
            )
        for i, value in enumerate(vec):
            summed[i] += value

    count = len(chunk_embeddings)
    mean = [value / count for value in summed]

    norm = math.sqrt(sum(v * v for v in mean))
    if norm == 0.0:
        # Degenerate: mean is the zero vector. Can only happen if every
        # input vector is exactly zero — embedders never produce that on
        # non-empty text, so raise rather than return an invalid unit.
        raise ValueError("Pooled embedding has zero norm; refusing to normalize.")

    return [v / norm for v in mean]
