"""F82.c: LlmChunkContextualizer unit tests.

Uses a mock ``LlmProvider`` so these tests are fast and offline.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.adapters.contextualizers.llm import LlmChunkContextualizer
from app.adapters.contextualizers.null import NullChunkContextualizer
from app.services.chunking import Chunk


class _RecordingLlm:
    """Records every call; returns canned per-call strings."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self._responses:
            return "default response"
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[idx]

    @property
    def model_name(self) -> str:
        return "test-llm"


class _FailingLlm:
    """Raises on every call — drives failure-handling paths."""

    def __init__(self) -> None:
        self.call_count = 0

    def complete(self, system: str, user: str) -> str:
        self.call_count += 1
        raise RuntimeError("simulated LLM failure")

    @property
    def model_name(self) -> str:
        return "failing-llm"


def _doc(*, filename: str = "doc.pdf", body: str = "doc body") -> Any:
    doc = MagicMock()
    doc.id = uuid4()
    doc.filename = filename
    doc.extracted_text = body
    return doc


def _chunk(text: str, idx: int) -> Chunk:
    return Chunk(text=text, metadata={"chunk_index": idx})


# ---------- mode: summary ----------


def test_summary_mode_makes_one_summary_plus_n_per_chunk_calls() -> None:
    llm = _RecordingLlm(responses=["SUMMARY"] + ["CTX_" + str(i) for i in range(3)])
    ctx = LlmChunkContextualizer(llm, mode="summary")
    doc = _doc(body="a" * 20_000)  # big so auto would also pick summary
    chunks = [_chunk(f"chunk {i}", i) for i in range(3)]

    result = ctx.contextualize(doc, chunks)

    assert len(llm.calls) == 4  # 1 summary + 3 chunks
    assert [c.context for c in result] == ["CTX_0", "CTX_1", "CTX_2"]
    # Every per-chunk call should reference the summary in its prompt.
    for call in llm.calls[1:]:
        assert "SUMMARY" in call[1]


# ---------- mode: full_doc ----------


def test_full_doc_mode_has_no_summary_call() -> None:
    llm = _RecordingLlm(responses=["CTX_" + str(i) for i in range(3)])
    ctx = LlmChunkContextualizer(llm, mode="full_doc")
    doc = _doc(body="full doc body text")
    chunks = [_chunk(f"chunk {i}", i) for i in range(3)]

    result = ctx.contextualize(doc, chunks)

    assert len(llm.calls) == 3  # no separate summary
    assert [c.context for c in result] == ["CTX_0", "CTX_1", "CTX_2"]
    for call in llm.calls:
        assert "full doc body text" in call[1]


# ---------- mode: auto ----------


def test_auto_mode_uses_full_doc_for_small_docs() -> None:
    llm = _RecordingLlm(responses=["CTX_" + str(i) for i in range(3)])
    ctx = LlmChunkContextualizer(llm, mode="auto", full_doc_max_chars=1000)
    doc = _doc(body="small doc body")  # ≤ 1000 chars
    chunks = [_chunk(f"chunk {i}", i) for i in range(3)]

    ctx.contextualize(doc, chunks)

    assert len(llm.calls) == 3  # full_doc path — no summary


def test_auto_mode_uses_summary_for_large_docs() -> None:
    llm = _RecordingLlm(responses=["SUMMARY"] + ["CTX_" + str(i) for i in range(3)])
    ctx = LlmChunkContextualizer(llm, mode="auto", full_doc_max_chars=100)
    doc = _doc(body="a" * 500)  # > 100 chars
    chunks = [_chunk(f"chunk {i}", i) for i in range(3)]

    ctx.contextualize(doc, chunks)

    assert len(llm.calls) == 4  # 1 summary + 3 per chunk


# ---------- failure handling ----------


def test_summary_failure_falls_back_to_filename_prefix() -> None:
    """Summary LLM call raises; per-chunk calls still run with a safe fallback context."""

    class SummaryFailsButChunksSucceed:
        def __init__(self) -> None:
            self.call_count = 0

        def complete(self, system: str, user: str) -> str:
            self.call_count += 1
            if self.call_count == 1:  # the summary call
                raise RuntimeError("summary down")
            return f"CTX_{self.call_count - 2}"

        @property
        def model_name(self) -> str:
            return "mock"

    llm = SummaryFailsButChunksSucceed()
    ctx = LlmChunkContextualizer(llm, mode="summary")
    doc = _doc(filename="thing.pdf", body="body" * 100)
    chunks = [_chunk(f"chunk {i}", i) for i in range(2)]

    result = ctx.contextualize(doc, chunks)

    # Both per-chunk calls still fired; got contexts despite the
    # summary failing and being replaced with a filename fallback.
    assert [c.context for c in result] == ["CTX_0", "CTX_1"]


def test_per_chunk_failure_leaves_context_none_without_breaking_others() -> None:
    """One bad chunk doesn't fail the whole doc."""

    class FailsOnSecondChunk:
        def __init__(self) -> None:
            self.call_count = 0

        def complete(self, system: str, user: str) -> str:
            self.call_count += 1
            if self.call_count == 2:  # summary=1, first chunk=2
                raise RuntimeError("chunk failed")
            return f"CTX_{self.call_count}"

        @property
        def model_name(self) -> str:
            return "mock"

    llm = FailsOnSecondChunk()
    ctx = LlmChunkContextualizer(llm, mode="summary")
    doc = _doc(body="body" * 100)
    chunks = [_chunk(f"chunk {i}", i) for i in range(3)]

    result = ctx.contextualize(doc, chunks)

    # First chunk was the failing call — context stays None.
    # Others get their canned responses.
    assert result[0].context is None
    assert result[1].context == "CTX_3"
    assert result[2].context == "CTX_4"


def test_all_calls_fail_all_contexts_none() -> None:
    llm = _FailingLlm()
    ctx = LlmChunkContextualizer(llm, mode="full_doc")
    doc = _doc()
    chunks = [_chunk(f"chunk {i}", i) for i in range(3)]

    result = ctx.contextualize(doc, chunks)

    assert all(c.context is None for c in result)
    assert llm.call_count == 3  # still attempted each chunk


# ---------- edge cases ----------


def test_empty_chunks_returns_empty() -> None:
    llm = _RecordingLlm(responses=[])
    ctx = LlmChunkContextualizer(llm)
    assert ctx.contextualize(_doc(), []) == []
    assert len(llm.calls) == 0


def test_chunk_text_and_metadata_preserved() -> None:
    """Contextualization must not mutate chunk text or metadata."""
    llm = _RecordingLlm(responses=["SUMMARY", "CTX"])
    ctx = LlmChunkContextualizer(llm, mode="summary")
    original = Chunk(text="original text", metadata={"chunk_index": 0, "x": "y"})

    result = ctx.contextualize(_doc(body="b" * 500), [original])

    assert result[0].text == "original text"
    assert result[0].metadata == {"chunk_index": 0, "x": "y"}
    assert result[0].context == "CTX"


def test_invalid_mode_raises() -> None:
    with pytest.raises(ValueError):
        LlmChunkContextualizer(_RecordingLlm([]), mode="nonsense")


def test_model_name_delegates_to_llm() -> None:
    llm = _RecordingLlm([])
    ctx = LlmChunkContextualizer(llm)
    assert ctx.model_name == "test-llm"


# ---------- NullChunkContextualizer ----------


def test_null_contextualizer_passthrough() -> None:
    ctx = NullChunkContextualizer()
    chunks = [_chunk("a", 0), _chunk("b", 1)]
    assert ctx.contextualize(_doc(), chunks) == chunks
    assert ctx.model_name == "none"
