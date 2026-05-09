"""F103.e — RAG answer-layer prompt rendering, format-only.

These tests stub the LLM so they're fast and offline. They lock in
the *wire format* of the prompts the RAG path produces:

- The system prompt actually contains the F103.e numbered rules
  the eval harness later asserts are followed.
- The user prompt embeds chunks with the F103.d
  ``--- Document: filename (chunk N){author_clause} ---`` header
  shape, including the optional author clause.
- The user prompt ends with ``Question: <question>``.

Behavioural quality (does the LLM actually follow the rules?) is
tested separately by ``tests/eval/test_rag_answer_quality.py``,
which calls the real LLM and is gated on configuration.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

import pytest

from app.adapters.protocols import IntentResult, RetrievedChunk
from app.models import UserRole
from app.services.rag_service import RagService


def _normalised(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class _RecordingLlm:
    """Captures ``(system, user)`` per call. Returns a fixed answer
    so the RagService's downstream branches don't trip."""

    model_name = "stub"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return "stub-answer"

    async def stream(self, system: str, user: str):  # pragma: no cover
        if False:
            yield ""


class _StubRetriever:
    def __init__(
        self,
        chunks: list[RetrievedChunk],
        candidates: list[Any] | None = None,
    ) -> None:
        self._chunks = chunks
        self._candidates = candidates or []

    async def retrieve_chunks(
        self, *, actor: Any, query: str, document_ids, limit: int
    ) -> list[RetrievedChunk]:
        return self._chunks

    async def retrieve_candidate_summaries(
        self, *, actor: Any, query: str, limit: int
    ) -> list[Any]:
        # F104.a — empty by default; tests can pass a non-empty list
        # via the constructor when they want to exercise the
        # candidate-block render path.
        return list(self._candidates)[:limit]


class _StubClassifier:
    def __init__(self, intent: str = "general") -> None:
        self._intent = intent

    def classify(self, question: str) -> IntentResult:
        return IntentResult(intent=self._intent, confidence=0.9, runner_up=None)


class _StubUser:
    id = uuid4()
    role = UserRole.HR


def _chunk(
    *,
    filename: str = "alice_resume.pdf",
    chunk_index: int = 0,
    text: str = "Some chunk text.",
    authored_by_name: str | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=uuid4(),
        filename=filename,
        chunk_index=chunk_index,
        text=text,
        distance=0.1,
        score=0.9,
        authored_by_name=authored_by_name,
    )


# ---------- system prompt: F103.e rules ----------


@pytest.mark.asyncio
async def test_system_prompt_contains_all_six_rule_headers() -> None:
    llm = _RecordingLlm()
    rag = RagService(
        retriever=_StubRetriever([_chunk()]),
        llm=llm,
        classifier=_StubClassifier(),
    )

    await rag.query(actor=_StubUser(), question="anything")

    assert len(llm.calls) == 1
    system, _ = llm.calls[0]
    for header in (
        "1. Citations.",
        "2. Indirect evidence.",
        "3. Naming.",
        "4. Specificity and quantification.",
        "5. Multi-document claims.",
        "6. Fallback.",
    ):
        assert header in system, f"missing rule header: {header!r}"


@pytest.mark.asyncio
async def test_system_prompt_contains_load_bearing_rule_phrases() -> None:
    """Spot-checks for the F103.e additions. Catches a future
    refactor that drops the words but keeps the headers."""
    llm = _RecordingLlm()
    rag = RagService(
        retriever=_StubRetriever([_chunk()]),
        llm=llm,
        classifier=_StubClassifier(),
    )

    await rag.query(actor=_StubUser(), question="anything")

    system = _normalised(llm.calls[0][0])
    assert "exactly one named candidate" in system
    assert "never blend attributions" in system
    assert "strongest specific claim" in system
    assert "two or more cited documents" in system
    assert "Not in the provided documents." in system


# ---------- user prompt: chunk header shape (F103.d carry-over) ----------


@pytest.mark.asyncio
async def test_user_prompt_renders_chunk_header_with_author() -> None:
    llm = _RecordingLlm()
    rag = RagService(
        retriever=_StubRetriever(
            [
                _chunk(
                    filename="cv.pdf",
                    chunk_index=2,
                    authored_by_name="Zain Ul Hassan",
                )
            ]
        ),
        llm=llm,
        classifier=_StubClassifier(),
    )

    await rag.query(actor=_StubUser(), question="anything")

    _, user = llm.calls[0]
    # F103.d header shape with author clause appended.
    assert "--- Document: cv.pdf (chunk 2) — Authored by: Zain Ul Hassan ---" in user


@pytest.mark.asyncio
async def test_user_prompt_renders_chunk_header_without_author() -> None:
    """When ``authored_by_name`` is None (case-study without F103.c
    linkage), the header has no Authored-by clause."""
    llm = _RecordingLlm()
    rag = RagService(
        retriever=_StubRetriever([_chunk(filename="case_study.pdf", chunk_index=4)]),
        llm=llm,
        classifier=_StubClassifier(),
    )

    await rag.query(actor=_StubUser(), question="anything")

    _, user = llm.calls[0]
    assert "--- Document: case_study.pdf (chunk 4) ---" in user
    assert "Authored by" not in user


@pytest.mark.asyncio
async def test_user_prompt_ends_with_question() -> None:
    llm = _RecordingLlm()
    rag = RagService(
        retriever=_StubRetriever([_chunk()]),
        llm=llm,
        classifier=_StubClassifier(),
    )

    await rag.query(actor=_StubUser(), question="who has stripe experience?")

    _, user = llm.calls[0]
    assert user.rstrip().endswith("Question: who has stripe experience?")


@pytest.mark.asyncio
async def test_user_prompt_includes_each_chunk_in_order() -> None:
    """RagService preserves the retriever's order so downstream
    debugging (citation order in the answer matches retrieval order)
    stays predictable."""
    llm = _RecordingLlm()
    rag = RagService(
        retriever=_StubRetriever(
            [
                _chunk(filename="a.pdf", chunk_index=0, text="alpha"),
                _chunk(filename="b.pdf", chunk_index=1, text="beta"),
                _chunk(filename="c.pdf", chunk_index=2, text="gamma"),
            ]
        ),
        llm=llm,
        classifier=_StubClassifier(),
    )

    await rag.query(actor=_StubUser(), question="anything")

    _, user = llm.calls[0]
    # Each chunk's text appears, in the retrieved order.
    idx_a = user.find("alpha")
    idx_b = user.find("beta")
    idx_c = user.find("gamma")
    assert 0 <= idx_a < idx_b < idx_c
