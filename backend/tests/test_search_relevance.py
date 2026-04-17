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
from app.models import Document, DocumentStatus, DocumentType
from app.services.search_service import SearchService, _confidence_band

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeVectorStore:
    """Returns a fixed list of hits regardless of the query."""

    def __init__(self, hits: list[VectorHit]) -> None:
        self._hits = hits
        self.last_query: str | None = None

    def query(
        self, query_text: str, n_results: int = 10, where: dict[str, Any] | None = None
    ) -> list[VectorHit]:
        self.last_query = query_text
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


def _mock_repo(docs: list[Document]) -> AsyncMock:
    repo = AsyncMock()
    repo.search_by_metadata = AsyncMock(return_value=[])
    repo.get_many = AsyncMock(return_value={d.id: d for d in docs})
    return repo


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

    results, _ = await service.search(query="anything")

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

    await service.search(query="anything at all")

    repo.search_by_metadata.assert_not_called()


async def test_sql_path_runs_when_skills_filter_provided() -> None:
    store = _FakeVectorStore([])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.search(query="python dev", skills=["python"])

    repo.search_by_metadata.assert_awaited_once()


async def test_sql_path_runs_when_document_type_filter_provided() -> None:
    store = _FakeVectorStore([])
    repo = _mock_repo([])
    service = SearchService(repo, store)

    await service.search(query="q3 report", document_type=DocumentType.REPORT)

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

    results, _ = await service.search(query="anything")

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

    results, _ = await service.search(query="anything")

    highlights = results[0]["highlights"]
    assert len(highlights) == 3  # capped
    assert len({h["chunk_index"] for h in highlights}) == 3  # no dups
