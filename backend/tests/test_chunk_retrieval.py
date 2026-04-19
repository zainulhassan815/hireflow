"""F81.k: SearchService.retrieve_chunks — chunk-level hybrid retrieval for RAG.

These tests follow the pattern of ``test_search_relevance.py``: a
fake ``VectorStore`` (controllable hits) + a mocked ``DocumentRepository``
(controllable FTS + SQL results). Real Postgres and Chroma are not
needed — the goal is to lock in the chunk-level merge contract, not
to re-test the underlying retrieval sources.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.adapters.protocols import VectorHit
from app.core.config import settings
from app.models import Document, DocumentStatus, DocumentType, User, UserRole
from app.services.search_service import SearchService

# ---------------------------------------------------------------------------
# Fakes (mirrors test_search_relevance.py)
# ---------------------------------------------------------------------------


class _FakeVectorStore:
    """Returns a fixed list of hits regardless of the query."""

    def __init__(self, hits: list[VectorHit]) -> None:
        self._hits = hits
        self.last_where: dict[str, Any] | None = None

    def query(
        self, query_text: str, n_results: int = 10, where: dict[str, Any] | None = None
    ) -> list[VectorHit]:
        self.last_where = where
        return self._hits[:n_results]

    def upsert(self, *_: Any, **__: Any) -> None: ...

    def delete(self, *_: Any, **__: Any) -> None: ...


def _vector_hit(
    *, doc_id: UUID, distance: float, chunk_index: int = 0, text: str = "chunk text"
) -> VectorHit:
    return VectorHit(
        chunk_id=f"{doc_id}:{chunk_index}",
        document_id=str(doc_id),
        text=text,
        metadata={"document_id": str(doc_id), "chunk_index": chunk_index},
        distance=distance,
    )


def _document(
    doc_id: UUID,
    *,
    filename: str = "doc.pdf",
    owner_id: UUID | None = None,
) -> Document:
    return Document(
        id=doc_id,
        owner_id=owner_id or uuid4(),
        filename=filename,
        mime_type="application/pdf",
        size_bytes=1,
        storage_key=f"storage/{doc_id}",
        status=DocumentStatus.READY,
        document_type=DocumentType.RESUME,
        metadata_={},
    )


def _mock_repo(
    docs: list[Document],
    *,
    lexical_hits: list[tuple[Document, float]] | None = None,
    fuzzy_hits: list[tuple[Document, float]] | None = None,
) -> AsyncMock:
    repo = AsyncMock()
    repo.search_by_metadata = AsyncMock(return_value=[])
    repo.full_text_search = AsyncMock(return_value=lexical_hits or [])
    repo.fuzzy_search = AsyncMock(return_value=fuzzy_hits or [])
    repo.get_many = AsyncMock(return_value={d.id: d for d in docs})
    return repo


def _admin() -> User:
    return User(id=uuid4(), email="admin@test", role=UserRole.ADMIN)


def _hr(user_id: UUID | None = None) -> User:
    return User(id=user_id or uuid4(), email="hr@test", role=UserRole.HR)


# ---------------------------------------------------------------------------
# Happy path — vector-only retrieval returns ranked chunks
# ---------------------------------------------------------------------------


async def test_retrieve_chunks_returns_vector_hits_as_ranked_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plain vector retrieval: the chunks come back in rank order with
    filenames hydrated from the document rows."""
    monkeypatch.setattr(settings, "search_max_distance", 0.9)

    alice_id = uuid4()
    bob_id = uuid4()
    store = _FakeVectorStore(
        [
            _vector_hit(doc_id=alice_id, distance=0.1, text="alice chunk"),
            _vector_hit(doc_id=bob_id, distance=0.3, text="bob chunk"),
        ]
    )
    repo = _mock_repo(
        [
            _document(alice_id, filename="alice.pdf"),
            _document(bob_id, filename="bob.pdf"),
        ]
    )
    service = SearchService(repo, store)

    chunks = await service.retrieve_chunks(
        actor=_admin(), query="anything", document_ids=None, limit=5
    )

    assert [c.filename for c in chunks] == ["alice.pdf", "bob.pdf"]
    assert chunks[0].text == "alice chunk"
    assert chunks[0].distance == 0.1
    assert chunks[0].score > chunks[1].score  # RRF ranks by score desc


# ---------------------------------------------------------------------------
# Lexical boost — FTS rank raises vector chunks from the matching doc
# ---------------------------------------------------------------------------


async def test_lexical_hit_boosts_vector_chunk_from_same_doc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doc B is tied with Doc A on vector rank but also matches FTS —
    its chunks should rank above A's after the lexical boost."""
    monkeypatch.setattr(settings, "search_max_distance", 0.9)
    monkeypatch.setattr(settings, "rrf_weight_lexical", 2.0)
    monkeypatch.setattr(settings, "rrf_weight_vector", 1.0)

    alice_id = uuid4()
    bob_id = uuid4()
    store = _FakeVectorStore(
        [
            _vector_hit(doc_id=alice_id, distance=0.2, text="alice chunk"),
            _vector_hit(doc_id=bob_id, distance=0.2, text="bob chunk"),
        ]
    )
    bob_doc = _document(bob_id, filename="bob.pdf")
    repo = _mock_repo(
        [_document(alice_id, filename="alice.pdf"), bob_doc],
        lexical_hits=[(bob_doc, 0.8)],
    )
    service = SearchService(repo, store)

    chunks = await service.retrieve_chunks(
        actor=_admin(), query="bob", document_ids=None, limit=5
    )

    # Bob's chunk jumps ahead of Alice's after FTS boost.
    assert [c.filename for c in chunks] == ["bob.pdf", "alice.pdf"]


# ---------------------------------------------------------------------------
# FTS-only docs don't fabricate phantom chunks
# ---------------------------------------------------------------------------


async def test_fts_only_doc_without_vector_hit_is_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Doc matches FTS but has no vector chunks in the hit list —
    it must not appear in results (no phantom chunks to feed the LLM)."""
    monkeypatch.setattr(settings, "search_max_distance", 0.9)

    alice_id = uuid4()
    fts_only_id = uuid4()
    store = _FakeVectorStore(
        [_vector_hit(doc_id=alice_id, distance=0.2, text="alice chunk")]
    )
    fts_only_doc = _document(fts_only_id, filename="fts-only.pdf")
    repo = _mock_repo(
        [_document(alice_id, filename="alice.pdf"), fts_only_doc],
        lexical_hits=[(fts_only_doc, 0.9)],
    )
    service = SearchService(repo, store)

    chunks = await service.retrieve_chunks(
        actor=_admin(), query="anything", document_ids=None, limit=5
    )

    filenames = {c.filename for c in chunks}
    assert filenames == {"alice.pdf"}


# ---------------------------------------------------------------------------
# document_ids scoping
# ---------------------------------------------------------------------------


async def test_document_ids_filter_scopes_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "search_max_distance", 0.9)

    alice_id = uuid4()
    bob_id = uuid4()
    store = _FakeVectorStore(
        [
            _vector_hit(doc_id=alice_id, distance=0.1),
            _vector_hit(doc_id=bob_id, distance=0.2),
        ]
    )
    repo = _mock_repo(
        [
            _document(alice_id, filename="alice.pdf"),
            _document(bob_id, filename="bob.pdf"),
        ]
    )
    service = SearchService(repo, store)

    chunks = await service.retrieve_chunks(
        actor=_admin(),
        query="q",
        document_ids=[alice_id],
        limit=5,
    )

    assert [c.filename for c in chunks] == ["alice.pdf"]


# ---------------------------------------------------------------------------
# Ownership scoping
# ---------------------------------------------------------------------------


async def test_hr_user_only_sees_own_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-admin callers get an owner_id filter pushed into the vector
    ``where`` clause. SearchService doesn't need to know the doc
    ownership beyond propagating the filter — Chroma and the FTS repo
    enforce it downstream."""
    monkeypatch.setattr(settings, "search_max_distance", 0.9)

    user_id = uuid4()
    store = _FakeVectorStore([_vector_hit(doc_id=uuid4(), distance=0.1)])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.retrieve_chunks(
        actor=_hr(user_id=user_id),
        query="q",
        document_ids=None,
        limit=5,
    )

    # owner_id landed in the vector where clause.
    where = store.last_where or {}
    assert where.get("owner_id") == str(user_id)
    # owner_id was threaded into the FTS call too.
    repo.full_text_search.assert_awaited()
    fts_kwargs = repo.full_text_search.await_args.kwargs
    assert fts_kwargs.get("owner_id") == user_id


async def test_admin_bypass_has_no_owner_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin callers skip the owner filter — they see every doc."""
    monkeypatch.setattr(settings, "search_max_distance", 0.9)

    store = _FakeVectorStore([_vector_hit(doc_id=uuid4(), distance=0.1)])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.retrieve_chunks(actor=_admin(), query="q", document_ids=None, limit=5)

    where = store.last_where or {}
    assert "owner_id" not in where
    fts_kwargs = repo.full_text_search.await_args.kwargs
    assert fts_kwargs.get("owner_id") is None


# ---------------------------------------------------------------------------
# Empty-query short-circuit
# ---------------------------------------------------------------------------


async def test_whitespace_query_short_circuits() -> None:
    store = _FakeVectorStore([])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    chunks = await service.retrieve_chunks(
        actor=_admin(), query="   ", document_ids=None, limit=5
    )
    assert chunks == []
    # Neither retrieval source was called.
    repo.full_text_search.assert_not_called()
    repo.get_many.assert_not_called()


# ---------------------------------------------------------------------------
# Non-READY docs are filtered out
# ---------------------------------------------------------------------------


async def test_non_ready_docs_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vector hits may reference docs that have been demoted to
    PROCESSING/FAILED; those chunks must not surface (F86 equivalent
    for the RAG path)."""
    monkeypatch.setattr(settings, "search_max_distance", 0.9)

    ready_id = uuid4()
    stale_id = uuid4()
    store = _FakeVectorStore(
        [
            _vector_hit(doc_id=ready_id, distance=0.1),
            _vector_hit(doc_id=stale_id, distance=0.2),
        ]
    )

    stale_doc = _document(stale_id, filename="stale.pdf")
    stale_doc.status = DocumentStatus.PROCESSING
    repo = _mock_repo([_document(ready_id, filename="ready.pdf"), stale_doc])
    service = SearchService(repo, store)

    chunks = await service.retrieve_chunks(
        actor=_admin(), query="q", document_ids=None, limit=5
    )

    assert [c.filename for c in chunks] == ["ready.pdf"]
