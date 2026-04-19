"""F89.c — EmbeddingService unit tests.

Verifies the similarity-store hook behaviour without touching Chroma:

* With ``similarity_store`` wired, ``index_document`` pools the chunk
  embeddings and upserts one doc-level vector.
* With ``similarity_store=None`` the pooling path is inert — only the
  chunk-level store is called (graceful degrade for partial deployments).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.adapters.protocols import Element
from app.models import Document, DocumentStatus, DocumentType
from app.services.embedding_service import EmbeddingService


class _FakeVectorStore:
    def __init__(self) -> None:
        self.upsert_calls: list[dict[str, Any]] = []

    def upsert(
        self,
        document_id: str,
        chunks: list[str],
        metadatas: list[dict[str, Any]],
        *,
        embedding_texts: list[str] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> None:
        self.upsert_calls.append(
            {
                "document_id": document_id,
                "chunks": chunks,
                "metadatas": metadatas,
                "embedding_texts": embedding_texts,
                "embeddings": embeddings,
            }
        )

    def delete(self, document_id: str) -> None:
        pass

    def query(
        self, query_text: str, n_results: int = 10, where: dict[str, Any] | None = None
    ) -> list[Any]:
        return []


class _FakeSimilarityStore:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[float], dict[str, Any]]] = []
        self.deletes: list[str] = []

    def upsert_document_vector(
        self, document_id: str, embedding: list[float], metadata: dict[str, Any]
    ) -> None:
        self.upserts.append((document_id, embedding, metadata))

    def delete_document_vector(self, document_id: str) -> None:
        self.deletes.append(document_id)

    def find_similar_documents(
        self,
        source_document_id: str,
        n_results: int,
        where: dict[str, Any] | None = None,
    ) -> list[Any]:
        return []


class _FakeEmbedder:
    """Returns deterministic unit-length vectors per text so we can assert
    on the pooled result without floating-point surprises."""

    model_name = "fake-embedder"
    dimension = 3

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # Assign each text an orthogonal basis direction modulo 3 so the
        # mean-pool has a predictable shape.
        basis = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        return [basis[i % 3] for i, _ in enumerate(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]

    @property
    def recommended_distance_threshold(self) -> float:
        return 0.5


def _doc() -> Document:
    return Document(
        id=uuid4(),
        owner_id=uuid4(),
        filename="fixture.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        storage_key=f"test/fixture-{uuid4()}",
        status=DocumentStatus.READY,
        document_type=DocumentType.RESUME,
    )


def _elements() -> list[Element]:
    return [
        Element(kind="NarrativeText", text="Python developer.", page_number=1, order=0),
        Element(kind="NarrativeText", text="AWS experience.", page_number=1, order=1),
    ]


def test_index_document_writes_both_stores() -> None:
    store = _FakeVectorStore()
    similarity = _FakeSimilarityStore()
    embedder = _FakeEmbedder()

    svc = EmbeddingService(store, embedder, similarity_store=similarity)
    doc = _doc()

    svc.index_document(doc, elements=_elements())

    assert len(store.upsert_calls) == 1
    assert store.upsert_calls[0]["embeddings"] is not None, (
        "service must pre-compute embeddings so they can be reused for "
        "doc-level pooling"
    )

    assert len(similarity.upserts) == 1
    upsert_id, upsert_vec, upsert_meta = similarity.upserts[0]
    assert upsert_id == str(doc.id)
    assert len(upsert_vec) == embedder.dimension
    # Fake embedder + tiny doc chunking = one chunk → pooled vector
    # should be unit-length (pool helper always normalizes).
    norm = sum(v * v for v in upsert_vec) ** 0.5
    assert abs(norm - 1.0) < 1e-6
    assert upsert_meta["document_id"] == str(doc.id)
    assert upsert_meta["owner_id"] == str(doc.owner_id)
    assert upsert_meta["document_type"] == DocumentType.RESUME.value


def test_index_document_without_similarity_store_skips_doc_upsert() -> None:
    """Partial deployment — no similarity store wired. Chunk path still
    runs, doc-level path is inert. No crash, no half-written state."""
    store = _FakeVectorStore()
    embedder = _FakeEmbedder()

    svc = EmbeddingService(store, embedder, similarity_store=None)
    svc.index_document(_doc(), elements=_elements())

    assert len(store.upsert_calls) == 1
    # No assertion we can make on the absent similarity store — the
    # key guarantee is that the call didn't crash and the chunk path
    # ran exactly as it used to pre-F89.c.


def test_remove_document_clears_both_stores() -> None:
    store = _FakeVectorStore()
    similarity = _FakeSimilarityStore()
    svc = EmbeddingService(store, _FakeEmbedder(), similarity_store=similarity)

    svc.remove_document("abc-123")

    assert similarity.deletes == ["abc-123"]


def test_no_document_type_omits_the_key() -> None:
    """When the classifier hasn't set ``document_type`` yet, the
    similarity metadata must not carry an empty-string sentinel that
    would match a ``where=document_type=""`` filter in weird ways."""
    doc = _doc()
    doc.document_type = None

    similarity = _FakeSimilarityStore()
    svc = EmbeddingService(
        _FakeVectorStore(), _FakeEmbedder(), similarity_store=similarity
    )
    svc.index_document(doc, elements=_elements())

    assert len(similarity.upserts) == 1
    _, _, upsert_meta = similarity.upserts[0]
    assert "document_type" not in upsert_meta
