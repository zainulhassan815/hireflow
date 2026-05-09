"""F104.a — CandidateSummaryService unit tests.

Stub LLM + stub embedder + stub store. Exercises the service's
contract:

- Generates summary text and writes it + version stamp on success.
- Indexes the summary in the candidate-similarity store when an
  embedder + store are wired.
- Returns ``None`` (and never raises) on LLM failure.
- Skips the indexing step when embedder / store is unwired.
- Truncates a chatty LLM response to the column length.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.db import sync_engine
from app.models import Candidate
from app.services.candidate_summary_service import (
    SUMMARY_VERSION,
    CandidateSummaryService,
)


class _StubLlmCall:
    """Records the prompts and returns a canned response."""

    def __init__(self, response: str = "Alice — backend, 5+ yrs, FastAPI.") -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.response


class _RaisingLlmCall:
    def __call__(self, system: str, user: str) -> str:
        raise RuntimeError("simulated LLM outage")


class _StubEmbedder:
    model_name = "stub-embedder"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class _RecordingStore:
    """Captures upsert/delete calls to the candidate-similarity store."""

    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.deletes: list[str] = []

    def upsert_candidate_summary(
        self,
        candidate_id: str,
        summary: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> None:
        self.upserts.append(
            {
                "candidate_id": candidate_id,
                "summary": summary,
                "embedding": embedding,
                "metadata": metadata,
            }
        )

    def delete_candidate_summary(self, candidate_id: str) -> None:
        self.deletes.append(candidate_id)

    def query_candidate_summaries(self, *args, **kwargs):
        return []


def _seed_candidate(
    session: Session,
    *,
    owner_id,
    name: str = "Alice Ng",
    email: str = "alice@example.com",
    skills: list[str] | None = None,
    source_document_id=None,
) -> Candidate:
    candidate = Candidate(
        owner_id=owner_id,
        name=name,
        email=email,
        skills=skills or ["python", "fastapi"],
        source_document_id=source_document_id,
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


@pytest.mark.asyncio
async def test_writes_summary_and_version_on_success(admin_user) -> None:
    with Session(sync_engine) as session:
        candidate = _seed_candidate(session, owner_id=admin_user.id)
        llm = _StubLlmCall(
            "Alice Ng — backend engineer, 5+ yrs, FastAPI + Postgres heavy."
        )

        service = CandidateSummaryService(session, llm)
        result = service.generate_for(candidate, resume_text="resume body text")

        assert (
            result == "Alice Ng — backend engineer, 5+ yrs, FastAPI + Postgres heavy."
        )
        session.refresh(candidate)
        assert candidate.summary == result
        assert candidate.summary_version == SUMMARY_VERSION
        # System prompt was passed; recruiter-brief format key
        # markers should be present.
        assert "recruiter-brief" in llm.calls[0][0] or "summaries" in llm.calls[0][0]


@pytest.mark.asyncio
async def test_indexes_in_store_when_wired(admin_user) -> None:
    """Candidate without a source document still gets indexed —
    ``source_document_id`` is optional in the metadata."""
    with Session(sync_engine) as session:
        candidate = _seed_candidate(session, owner_id=admin_user.id)

        llm = _StubLlmCall("Alice — backend, 5+ yrs, FastAPI.")
        embedder = _StubEmbedder()
        store = _RecordingStore()

        service = CandidateSummaryService(session, llm, embedder=embedder, store=store)
        service.generate_for(candidate, resume_text="r")

        assert len(store.upserts) == 1
        upsert = store.upserts[0]
        assert upsert["candidate_id"] == str(candidate.id)
        assert upsert["summary"] == "Alice — backend, 5+ yrs, FastAPI."
        assert upsert["embedding"] == [0.1, 0.2, 0.3]
        assert upsert["metadata"]["owner_id"] == str(admin_user.id)
        assert upsert["metadata"]["summary_version"] == SUMMARY_VERSION
        # No source_document_id present when the candidate doesn't
        # have one.
        assert "source_document_id" not in upsert["metadata"]


@pytest.mark.asyncio
async def test_skips_indexing_when_store_unwired(admin_user) -> None:
    """Text write succeeds; index step short-circuits cleanly."""
    with Session(sync_engine) as session:
        candidate = _seed_candidate(session, owner_id=admin_user.id)
        llm = _StubLlmCall("Alice — backend.")

        service = CandidateSummaryService(session, llm)  # no embedder/store
        result = service.generate_for(candidate, resume_text="r")

        assert result == "Alice — backend."
        session.refresh(candidate)
        assert candidate.summary == "Alice — backend."


@pytest.mark.asyncio
async def test_returns_none_on_llm_failure(admin_user, caplog) -> None:
    """Service swallows LLM errors and returns None — caller's
    transaction must not roll back."""
    with Session(sync_engine) as session:
        candidate = _seed_candidate(session, owner_id=admin_user.id)
        service = CandidateSummaryService(session, _RaisingLlmCall())

        with caplog.at_level("ERROR", logger="app.services.candidate_summary_service"):
            result = service.generate_for(candidate, resume_text="r")

        assert result is None
        session.refresh(candidate)
        assert candidate.summary is None
        assert any(
            "candidate summary generation failed" in r.message for r in caplog.records
        )


@pytest.mark.asyncio
async def test_returns_none_on_empty_llm_response(admin_user) -> None:
    """LLM returned an empty string — leave the column NULL."""
    with Session(sync_engine) as session:
        candidate = _seed_candidate(session, owner_id=admin_user.id)
        service = CandidateSummaryService(session, _StubLlmCall(""))

        result = service.generate_for(candidate, resume_text="r")

        assert result is None
        session.refresh(candidate)
        assert candidate.summary is None
        assert candidate.summary_version is None


@pytest.mark.asyncio
async def test_truncates_chatty_llm_to_column_length(admin_user) -> None:
    """A 2000-char LLM response gets clipped to 1024 chars
    (the column length) — schema fail-mode is silent truncation."""
    with Session(sync_engine) as session:
        candidate = _seed_candidate(session, owner_id=admin_user.id)
        long_text = "A" * 2000
        service = CandidateSummaryService(session, _StubLlmCall(long_text))

        result = service.generate_for(candidate, resume_text="r")

        assert result is not None
        assert len(result) == 1024
        session.refresh(candidate)
        assert candidate.summary is not None
        assert len(candidate.summary) == 1024
