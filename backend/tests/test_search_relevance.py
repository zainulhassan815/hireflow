"""Targeted unit tests for the F80 search-scoring fixes.

These cover the three code-level invariants that, if they break,
return us to "every query returns everything." They use a tiny
in-memory fake ``VectorStore`` and a real ``DocumentRepository`` —
fast enough to run on every ``make test``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from app.adapters.protocols import VectorHit
from app.core.config import settings
from app.models import Document, DocumentStatus, DocumentType, User, UserRole
from app.services.search_service import SearchService, _confidence_band

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeVectorStore:
    """Returns a fixed list of hits regardless of the query."""

    def __init__(self, hits: list[VectorHit]) -> None:
        self._hits = hits
        self.last_query: str | None = None
        self.last_where: dict[str, Any] | None = None

    def query(
        self, query_text: str, n_results: int = 10, where: dict[str, Any] | None = None
    ) -> list[VectorHit]:
        self.last_query = query_text
        self.last_where = where
        return self._hits[:n_results]

    def upsert(self, *_: Any, **__: Any) -> None: ...

    def delete(self, *_: Any, **__: Any) -> None: ...


def _vector_hit(*, doc_id: UUID, distance: float, chunk_index: int = 0) -> VectorHit:
    return VectorHit(
        chunk_id=f"{doc_id}:{chunk_index}",
        document_id=str(doc_id),
        text=f"chunk text for {doc_id}",
        metadata={"document_id": str(doc_id), "chunk_index": chunk_index},
        distance=distance,
    )


def _document(doc_id: UUID, *, filename: str = "doc.pdf") -> Document:
    return Document(
        id=doc_id,
        owner_id=uuid4(),
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
) -> AsyncMock:
    repo = AsyncMock()
    repo.search_by_metadata = AsyncMock(return_value=[])
    repo.full_text_search = AsyncMock(return_value=lexical_hits or [])
    repo.get_many = AsyncMock(return_value={d.id: d for d in docs})
    return repo


def _admin() -> User:
    return User(id=uuid4(), email="admin@test", role=UserRole.ADMIN)


def _hr(user_id: UUID | None = None) -> User:
    return User(id=user_id or uuid4(), email="hr@test", role=UserRole.HR)


# ---------------------------------------------------------------------------
# Threshold filter
# ---------------------------------------------------------------------------


async def test_hits_above_distance_threshold_are_dropped(monkeypatch) -> None:
    """The original 'everything matches' bug: far hits sneak through."""
    monkeypatch.setattr(settings, "search_max_distance", 0.6)

    kept = uuid4()
    dropped = uuid4()

    store = _FakeVectorStore(
        [
            _vector_hit(doc_id=kept, distance=0.3),
            _vector_hit(doc_id=dropped, distance=0.9),
        ]
    )
    repo = _mock_repo([_document(kept), _document(dropped)])
    service = SearchService(repo, store)

    results, _ = await service.search(actor=_admin(), query="anything")

    returned_ids = {r["document_id"] for r in results}
    assert kept in returned_ids
    assert dropped not in returned_ids


# ---------------------------------------------------------------------------
# SQL path conditionality
# ---------------------------------------------------------------------------


async def test_sql_path_is_skipped_when_no_structured_filter() -> None:
    """Without filters, the SQL "recent docs" fallback must not run."""
    store = _FakeVectorStore([])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.search(actor=_admin(), query="anything at all")

    repo.search_by_metadata.assert_not_called()


async def test_sql_path_runs_when_skills_filter_provided() -> None:
    store = _FakeVectorStore([])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.search(actor=_admin(), query="python dev", skills=["python"])

    repo.search_by_metadata.assert_awaited_once()


async def test_sql_path_runs_when_document_type_filter_provided() -> None:
    store = _FakeVectorStore([])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.search(
        actor=_admin(), query="q3 report", document_type=DocumentType.REPORT
    )

    repo.search_by_metadata.assert_awaited_once()


# ---------------------------------------------------------------------------
# Confidence bands
# ---------------------------------------------------------------------------


def test_confidence_band_high_medium_low(monkeypatch) -> None:
    monkeypatch.setattr(settings, "search_confidence_high", 0.02)
    monkeypatch.setattr(settings, "search_confidence_medium", 0.01)

    assert _confidence_band(0.05) == "high"
    assert _confidence_band(0.02) == "high"  # inclusive on boundary
    assert _confidence_band(0.015) == "medium"
    assert _confidence_band(0.01) == "medium"
    assert _confidence_band(0.001) == "low"
    assert _confidence_band(0.0) == "low"


async def test_result_includes_confidence_but_not_raw_score() -> None:
    doc_id = uuid4()
    store = _FakeVectorStore([_vector_hit(doc_id=doc_id, distance=0.1)])
    repo = _mock_repo([_document(doc_id)])
    service = SearchService(repo, store)

    results, _ = await service.search(actor=_admin(), query="anything")

    assert len(results) == 1
    assert "confidence" in results[0]
    assert results[0]["confidence"] in ("high", "medium", "low")
    # `score` was the normalized lie; it should no longer appear.
    assert "score" not in results[0]


# ---------------------------------------------------------------------------
# Highlight dedup + cap
# ---------------------------------------------------------------------------


async def test_highlights_are_deduped_and_capped(monkeypatch) -> None:
    monkeypatch.setattr(settings, "search_max_highlights_per_doc", 3)

    doc_id = uuid4()
    # 5 chunks, 2 of them are duplicates (chunk_index collides).
    hits = [
        _vector_hit(doc_id=doc_id, distance=0.1, chunk_index=0),
        _vector_hit(doc_id=doc_id, distance=0.15, chunk_index=1),
        _vector_hit(doc_id=doc_id, distance=0.2, chunk_index=1),  # dup
        _vector_hit(doc_id=doc_id, distance=0.25, chunk_index=2),
        _vector_hit(doc_id=doc_id, distance=0.3, chunk_index=3),
    ]
    store = _FakeVectorStore(hits)
    repo = _mock_repo([_document(doc_id)])
    service = SearchService(repo, store)

    results, _ = await service.search(actor=_admin(), query="anything")

    highlights = results[0]["highlights"]
    assert len(highlights) == 3  # capped
    assert len({h["chunk_index"] for h in highlights}) == 3  # no dups


# ---------------------------------------------------------------------------
# F85 lexical / hybrid retrieval
# ---------------------------------------------------------------------------


async def test_lexical_only_doc_surfaces_when_vector_returns_nothing() -> None:
    """The 'single-word python' eval failure: vector misses, lexical catches."""
    lex_id = uuid4()
    store = _FakeVectorStore([])  # vector returns nothing
    repo = _mock_repo(
        [_document(lex_id, filename="python_resume.pdf")],
        lexical_hits=[(_document(lex_id), 0.42)],
    )
    service = SearchService(repo, store)

    results, _ = await service.search(actor=_admin(), query="python")

    assert len(results) == 1
    assert results[0]["document_id"] == lex_id


async def test_hybrid_doc_outranks_single_signal_doc() -> None:
    """A doc surfaced by both vector + lexical must rank above a single-source doc."""
    both = uuid4()
    vector_only = uuid4()

    store = _FakeVectorStore(
        [
            _vector_hit(doc_id=both, distance=0.1),
            _vector_hit(doc_id=vector_only, distance=0.15),
        ]
    )
    repo = _mock_repo(
        [_document(both), _document(vector_only)],
        # `both` is also the top lexical hit.
        lexical_hits=[(_document(both), 0.5)],
    )
    service = SearchService(repo, store)

    results, _ = await service.search(actor=_admin(), query="anything")

    assert [r["document_id"] for r in results][:2] == [both, vector_only]


async def test_lexical_search_called_with_user_query() -> None:
    store = _FakeVectorStore([])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.search(actor=_admin(), query="vendor services agreement")

    repo.full_text_search.assert_awaited_once()
    args, kwargs = repo.full_text_search.call_args
    # Query is the first positional arg.
    assert args[0] == "vendor services agreement"


# ---------------------------------------------------------------------------
# F86 ownership scoping
# ---------------------------------------------------------------------------


async def test_admin_search_passes_no_owner_filter() -> None:
    """Admins must see every document — no owner_id propagated."""
    store = _FakeVectorStore([])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.search(actor=_admin(), query="anything")

    # FTS path must not get an owner filter for admins.
    _, kwargs = repo.full_text_search.call_args
    assert kwargs.get("owner_id") is None


async def test_hr_search_propagates_owner_filter_to_fts() -> None:
    """Non-admins get scoped to their own owner_id in every retrieval path."""
    actor = _hr()
    store = _FakeVectorStore([])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.search(actor=actor, query="anything")

    _, kwargs = repo.full_text_search.call_args
    assert kwargs["owner_id"] == actor.id


async def test_hr_search_propagates_owner_filter_to_metadata_path() -> None:
    """Same scoping must reach search_by_metadata when filters are present."""
    actor = _hr()
    store = _FakeVectorStore([])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.search(actor=actor, query="python", skills=["python"])

    _, kwargs = repo.search_by_metadata.call_args
    assert kwargs["owner_id"] == actor.id


async def test_hr_search_propagates_owner_filter_to_vector_where() -> None:
    """The Chroma `where` clause must include owner_id for non-admin actors."""
    actor = _hr()
    store = _FakeVectorStore([])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.search(actor=actor, query="anything")

    # Single-condition where collapses to a flat dict; with owner_id only
    # we expect exactly that one key.
    where = store.last_where
    assert where == {"owner_id": str(actor.id)}


async def test_hr_search_combines_owner_and_document_type_in_vector_where() -> None:
    """Multi-condition where uses Chroma's $and operator."""
    actor = _hr()
    store = _FakeVectorStore([])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.search(
        actor=actor, query="anything", document_type=DocumentType.RESUME
    )

    assert store.last_where == {
        "$and": [
            {"document_type": DocumentType.RESUME.value},
            {"owner_id": str(actor.id)},
        ]
    }
