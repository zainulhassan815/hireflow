"""F85.a: tests for the embedding-provider abstraction.

Loads a real sentence-transformer model (bge-small, ~80MB) once per
session and exercises the adapter. If the model isn't already cached
locally, the first test run downloads it — factor that into CI timing.
"""

from __future__ import annotations

import pytest

from app.adapters.embeddings.sentence_transformer import SentenceTransformerEmbedder


@pytest.fixture(scope="module")
def embedder() -> SentenceTransformerEmbedder:
    """One model per module — the load is slow; don't repeat it."""
    return SentenceTransformerEmbedder(model_name="BAAI/bge-small-en-v1.5")


def test_dimension_matches_expected(embedder: SentenceTransformerEmbedder) -> None:
    # bge-small-en-v1.5 is a 384-dim model.
    assert embedder.dimension == 384


def test_model_name_round_trips(embedder: SentenceTransformerEmbedder) -> None:
    assert embedder.model_name == "BAAI/bge-small-en-v1.5"


def test_embed_query_returns_correct_shape(
    embedder: SentenceTransformerEmbedder,
) -> None:
    vec = embedder.embed_query("Senior Python engineer")
    assert isinstance(vec, list)
    assert len(vec) == embedder.dimension
    assert all(isinstance(x, float) for x in vec)


def test_embed_documents_returns_one_vector_per_input(
    embedder: SentenceTransformerEmbedder,
) -> None:
    vecs = embedder.embed_documents(
        [
            "Senior Python engineer with Kubernetes.",
            "Quarterly sales report — EMEA.",
        ]
    )
    assert len(vecs) == 2
    assert all(len(v) == embedder.dimension for v in vecs)


def test_embed_documents_on_empty_input(
    embedder: SentenceTransformerEmbedder,
) -> None:
    assert embedder.embed_documents([]) == []


def test_same_text_yields_deterministic_output(
    embedder: SentenceTransformerEmbedder,
) -> None:
    a = embedder.embed_query("hello world")
    b = embedder.embed_query("hello world")
    assert a == b


def test_different_texts_yield_different_vectors(
    embedder: SentenceTransformerEmbedder,
) -> None:
    a = embedder.embed_query("Senior Python engineer")
    b = embedder.embed_query("Quarterly sales report")
    assert a != b


def test_lazy_load_defers_model_until_first_call() -> None:
    """Constructing the adapter must NOT load the 80MB model."""
    fresh = SentenceTransformerEmbedder(model_name="BAAI/bge-small-en-v1.5")
    # The private field is named for exactly this introspection.
    assert fresh._model is None
    # Touching .model_name is fine — it's just the stored string.
    _ = fresh.model_name
    assert fresh._model is None
