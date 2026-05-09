"""F103.c — RAG context block surfaces author when SearchService
hydrated one. Tests the ``_CONTEXT_TEMPLATE`` change in isolation by
stubbing the retriever; full hydration coverage lives in
``test_search_service_author_hydration``.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.adapters.protocols import RetrievedChunk
from app.models import UserRole
from app.services.rag_service import RagService


class _StubRetriever:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self._chunks = chunks

    async def retrieve_chunks(
        self, *, actor: Any, query: str, document_ids, limit: int
    ) -> list[RetrievedChunk]:
        return self._chunks

    async def retrieve_candidate_summaries(
        self, *, actor: Any, query: str, limit: int
    ) -> list[Any]:
        # F104.a — these tests pre-date the candidate lane and don't
        # exercise it; empty list keeps the parent code path's
        # "fallback to chunks" branch active.
        return []


class _StubLlm:
    model_name = "stub-model"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        # Tests inspect the prompts via the captured kwargs after a call.
        self.last_system = system_prompt
        self.last_user = user_prompt
        return "stub-answer"

    async def stream(self, system_prompt: str, user_prompt: str):
        # Async generator must yield at least once for the type checker.
        if False:
            yield ""


class _StubClassifier:
    def classify(self, question: str):
        from app.adapters.protocols import IntentResult

        return IntentResult(intent="general", confidence=0.99, runner_up=None)


class _StubUser:
    id = uuid4()
    role = UserRole.HR


def _make_chunk(*, authored_by_name: str | None) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=uuid4(),
        filename="case_study.pdf",
        chunk_index=0,
        text="We built a Stripe integration handling $2M/mo.",
        distance=0.1,
        score=0.9,
        authored_by_name=authored_by_name,
    )


@pytest.mark.asyncio
async def test_context_includes_authored_by_when_set() -> None:
    chunk = _make_chunk(authored_by_name="Alice Ng")
    service = RagService(
        retriever=_StubRetriever([chunk]),
        llm=_StubLlm(),
        classifier=_StubClassifier(),
    )

    ctx = await service._build_context(
        actor=_StubUser(),
        question="who built the stripe integration?",
        document_ids=None,
        max_chunks=5,
    )

    assert ctx is not None
    assert "Authored by: Alice Ng" in ctx.user_prompt
    assert "case_study.pdf" in ctx.user_prompt


@pytest.mark.asyncio
async def test_context_omits_authored_by_when_unknown() -> None:
    chunk = _make_chunk(authored_by_name=None)
    service = RagService(
        retriever=_StubRetriever([chunk]),
        llm=_StubLlm(),
        classifier=_StubClassifier(),
    )

    ctx = await service._build_context(
        actor=_StubUser(),
        question="who built the stripe integration?",
        document_ids=None,
        max_chunks=5,
    )

    assert ctx is not None
    assert "Authored by:" not in ctx.user_prompt
    # Header still has the filename + chunk index, just no clause.
    assert "case_study.pdf (chunk 0) ---" in ctx.user_prompt
