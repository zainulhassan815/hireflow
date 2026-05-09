"""F103.e — RAG answer-quality eval harness.

Hits the real LLM via ``RagService`` against a small set of labeled
``(question, chunks, expected-properties)`` fixtures. Each fixture
asserts substring must-include / must-not-include rules; a fixture
passes iff *every* assertion holds. The eval as a whole passes iff
at least ``RAG_ANSWER_FIXTURE_PASS_THRESHOLD`` of fixtures pass.

Skipped when no LLM provider is configured — this eval is for
guarding the prompt against regressions, not a hard CI requirement.
The unit tests in ``test_rag_answer_prompt_format.py`` cover the
deterministic prompt-rendering surface.

Run with ``make eval-rag-answer``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.adapters.protocols import RetrievedChunk
from app.core.config import settings
from app.models import UserRole
from app.services.rag_service import RagService

# Per-fixture pass/fail. A fixture passes iff every must / must_not
# assertion holds. Eval passes overall iff this fraction of fixtures
# pass. Tunable; first run sets the baseline. 0.80 chosen so a 5-
# fixture suite can lose one fixture without failing CI; an 8-fixture
# suite can lose ~1.6 (rounds to 1).
RAG_ANSWER_FIXTURE_PASS_THRESHOLD = 0.80


def _build_llm():
    """Mirror the runtime LLM-provider selection from
    ``app.api.deps``. Returns ``None`` if no provider is configured."""
    provider = (settings.llm_provider or "").lower()
    if provider == "anthropic" and settings.anthropic_api_key:
        from app.adapters.llm.claude import ClaudeLlmProvider

        return ClaudeLlmProvider(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
        )
    return None


def _build_intent_classifier():
    """Use the production intent classifier so the right format-rule
    branch lights up. Imports the registry-built singleton via
    ``app.api.deps``; that module is import-safe."""
    from app.api import deps

    return deps._intent_classifier


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
        # F104.a — eval fixtures don't include candidate hits today;
        # the chunk-only path remains the load-bearing eval signal.
        return []


class _StubUser:
    id = uuid4()
    role = UserRole.HR


def _chunk_from_fixture(record: dict) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=uuid4(),
        filename=record["filename"],
        chunk_index=record["chunk_index"],
        text=record["text"],
        # Distance below the high-confidence band so the answer path
        # doesn't deflect on the gate. Eval is about prompt
        # adherence, not retrieval-confidence behaviour.
        distance=0.10,
        score=0.90,
        authored_by_name=record.get("authored_by_name"),
    )


def _load_cases() -> list[dict]:
    path = Path(__file__).parent / "rag_answer_cases.json"
    with path.open() as f:
        cases = json.load(f)
    assert isinstance(cases, list) and cases
    return cases


def _evaluate_fixture(rag: RagService, case: dict) -> tuple[bool, str, list[str]]:
    """Run one fixture; return ``(passed, answer, failed_props)``."""
    chunks = [_chunk_from_fixture(r) for r in case["chunks"]]

    async def _run() -> str:
        retriever = _StubRetriever(chunks)
        local_rag = RagService(
            retriever=retriever, llm=rag._llm, classifier=rag._classifier
        )
        result = await local_rag.query(actor=_StubUser(), question=case["question"])
        return result.answer

    answer = asyncio.run(_run())

    failed: list[str] = []
    for needed in case.get("must_include", []):
        if needed not in answer:
            failed.append(f"missing must_include: {needed!r}")
    for forbidden in case.get("must_not_include", []):
        if forbidden in answer:
            failed.append(f"contains must_not_include: {forbidden!r}")

    return (not failed, answer, failed)


def test_rag_answer_quality() -> None:
    llm = _build_llm()
    if llm is None:
        pytest.skip("no LLM provider configured (set LLM_PROVIDER + key)")

    classifier = _build_intent_classifier()
    cases = _load_cases()

    rag = RagService(retriever=_StubRetriever([]), llm=llm, classifier=classifier)

    passed = 0
    per_case_lines: list[str] = []
    for case in cases:
        ok, answer, failures = _evaluate_fixture(rag, case)
        if ok:
            passed += 1
            per_case_lines.append(f"  ✔ {case['name']}")
        else:
            per_case_lines.append(f"  ✘ {case['name']}")
            for f in failures:
                per_case_lines.append(f"      - {f}")
            # Truncated answer for log triage.
            snippet = answer[:200].replace("\n", " ")
            per_case_lines.append(f"      answer: {snippet!r}")

    total = len(cases)
    pass_rate = passed / total

    print("\nRAG answer-quality eval")
    print(f"  fixtures: {passed}/{total} passed ({pass_rate:.0%})")
    for line in per_case_lines:
        print(line)

    assert pass_rate >= RAG_ANSWER_FIXTURE_PASS_THRESHOLD, (
        f"RAG answer fixture pass-rate {pass_rate:.0%} below threshold "
        f"{RAG_ANSWER_FIXTURE_PASS_THRESHOLD:.0%}"
    )
