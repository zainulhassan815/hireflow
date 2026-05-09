"""F82.c + F103.d — LlmChunkContextualizer unit tests.

Uses a hand-rolled stub ``LlmProvider`` and a typed-attribute
fake ``Document`` so the contextualizer reads real strings rather
than MagicMock children. Covers:

- F82.c modes (summary / full_doc / auto), failure handling, edge
  cases.
- F103.d entity-aware prompt rendering: author + tech slots,
  fallback ordering, skills truncation, system-prompt instructions.
- F103.d version stamp on success path; null contextualizer's
  distinct stamp value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from app.adapters.contextualizers.llm import (
    CONTEXTUALIZATION_VERSION,
    LlmChunkContextualizer,
    _resolve_author,
    _resolve_tech_clause,
)
from app.adapters.contextualizers.null import NullChunkContextualizer
from app.services.chunking import Chunk

# ---------- fakes ----------


class _RecordingLlm:
    """Records every call; returns canned per-call strings."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = responses or []
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


@dataclass
class _FakeCandidate:
    name: str | None


class _FakeDocument:
    """Typed-attribute Document stand-in. Production ``Document``
    instances trigger SA's machinery; the contextualizer only reads
    attributes, so a plain class is enough."""

    def __init__(
        self,
        *,
        filename: str = "doc.pdf",
        body: str = "doc body",
        metadata: dict[str, Any] | None = None,
        authored_by: _FakeCandidate | None = None,
    ) -> None:
        self.id = uuid4()
        self.filename = filename
        self.extracted_text = body
        self.metadata_: dict[str, Any] | None = (
            None if metadata is None else dict(metadata)
        )
        self.authored_by = authored_by


def _doc(*, filename: str = "doc.pdf", body: str = "doc body") -> _FakeDocument:
    return _FakeDocument(filename=filename, body=body)


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


# ---------- F103.d: author resolution ----------


def test_author_uses_authored_by_when_present() -> None:
    doc = _FakeDocument(authored_by=_FakeCandidate(name="Alice Ng"))
    assert _resolve_author(doc) == "Alice Ng"


def test_author_falls_back_to_metadata_name(caplog) -> None:
    doc = _FakeDocument(metadata={"name": "Bob Smith"})
    with caplog.at_level("INFO", logger="app.adapters.contextualizers.llm"):
        assert _resolve_author(doc) == "Bob Smith"
    assert any("metadata.name fallback" in r.message for r in caplog.records)


def test_author_unknown_when_neither_source(caplog) -> None:
    doc = _FakeDocument(metadata=None, authored_by=None)
    with caplog.at_level("INFO", logger="app.adapters.contextualizers.llm"):
        assert _resolve_author(doc) == "unknown"
    # No fallback log when there's nothing to fall back to.
    assert not any("metadata.name fallback" in r.message for r in caplog.records)


def test_author_prefers_authored_by_over_metadata() -> None:
    """Linked candidate name beats metadata copy — single source of truth."""
    doc = _FakeDocument(
        authored_by=_FakeCandidate(name="Alice Linked"),
        metadata={"name": "Alice Stale"},
    )
    assert _resolve_author(doc) == "Alice Linked"


def test_author_skips_authored_by_with_null_name() -> None:
    """``authored_by`` row with ``name=None`` falls through to
    metadata fallback rather than rendering 'None'."""
    doc = _FakeDocument(
        authored_by=_FakeCandidate(name=None),
        metadata={"name": "From Metadata"},
    )
    assert _resolve_author(doc) == "From Metadata"


# ---------- F103.d: tech clause ----------


def test_tech_clause_renders_sorted_skills() -> None:
    doc = _FakeDocument(metadata={"skills": ["stripe", "fastapi", "postgres"]})
    assert _resolve_tech_clause(doc) == "fastapi, postgres, stripe"


def test_tech_clause_empty_when_no_skills() -> None:
    doc = _FakeDocument(metadata={"skills": []})
    assert _resolve_tech_clause(doc) == "(none extracted)"


def test_tech_clause_truncates_with_explicit_count() -> None:
    skills = [f"skill_{i:03d}" for i in range(60)]
    doc = _FakeDocument(metadata={"skills": skills})
    clause = _resolve_tech_clause(doc)
    assert "…and 10 more" in clause


# ---------- F103.d: prompt rendering ----------


def test_summary_prompt_has_author_and_tech_slots() -> None:
    llm = _RecordingLlm(responses=["SUMMARY", "CTX"])
    ctx = LlmChunkContextualizer(llm, mode="summary")
    doc = _FakeDocument(
        body="a" * 500,
        authored_by=_FakeCandidate(name="Alice Ng"),
        metadata={"skills": ["stripe", "fastapi"]},
    )

    ctx.contextualize(doc, [_chunk("c", 0)])

    # First call is the doc-level summary; second is the per-chunk
    # situate. Both should carry the same author + tech clauses.
    summary_user, situate_user = llm.calls[0][1], llm.calls[1][1]
    assert "Author: Alice Ng" in summary_user
    assert "Technologies mentioned in this document: fastapi, stripe" in summary_user
    assert "Author: Alice Ng" in situate_user
    assert "Technologies mentioned in this document: fastapi, stripe" in situate_user


def test_unknown_author_renders_as_unknown_clause() -> None:
    llm = _RecordingLlm(responses=["CTX"])
    ctx = LlmChunkContextualizer(llm, mode="full_doc")
    doc = _FakeDocument(body="x", metadata={"skills": []})

    ctx.contextualize(doc, [_chunk("c", 0)])

    user_prompt = llm.calls[0][1]
    assert "Author: unknown" in user_prompt
    assert "Technologies mentioned in this document: (none extracted)" in user_prompt


def test_situate_system_prompt_instructs_preserve_agency() -> None:
    """String-content assertion. We don't have a way to test LLM
    output for actual agency preservation without a real eval; this
    is honest about scope — we're verifying the prompt instructs the
    right thing."""
    llm = _RecordingLlm(responses=["CTX"])
    ctx = LlmChunkContextualizer(llm, mode="full_doc")

    ctx.contextualize(_FakeDocument(body="x"), [_chunk("c", 0)])

    assert "Preserve agency" in llm.calls[0][0]


def test_summarizer_system_prompt_instructs_preserve_agency() -> None:
    llm = _RecordingLlm(responses=["SUMMARY", "CTX"])
    ctx = LlmChunkContextualizer(llm, mode="summary")

    ctx.contextualize(_FakeDocument(body="b" * 500), [_chunk("c", 0)])

    # Summary call is index 0.
    assert "Preserve agency" in llm.calls[0][0]


# ---------- F103.d: version stamp ----------


def test_contextualize_stamps_version_on_metadata() -> None:
    llm = _RecordingLlm(responses=["CTX"])
    ctx = LlmChunkContextualizer(llm, mode="full_doc")
    doc = _FakeDocument(body="x")

    ctx.contextualize(doc, [_chunk("c", 0)])

    assert doc.metadata_ is not None
    assert (
        doc.metadata_.get("contextualization_version")
        == CONTEXTUALIZATION_VERSION
        == "v2-haiku-entity-aware"
    )


def test_stamp_preserves_other_metadata_keys() -> None:
    llm = _RecordingLlm(responses=["CTX"])
    ctx = LlmChunkContextualizer(llm, mode="full_doc")
    doc = _FakeDocument(
        body="x",
        metadata={"skills": ["stripe"], "skill_extraction_version": "v1-narrative"},
    )

    ctx.contextualize(doc, [_chunk("c", 0)])

    assert doc.metadata_["skills"] == ["stripe"]
    assert doc.metadata_["skill_extraction_version"] == "v1-narrative"
    assert doc.metadata_["contextualization_version"] == "v2-haiku-entity-aware"


def test_stamp_skipped_when_chunks_empty() -> None:
    """No chunks means nothing was contextualized — don't lie about
    the version."""
    llm = _RecordingLlm(responses=[])
    ctx = LlmChunkContextualizer(llm, mode="full_doc")
    doc = _FakeDocument(body="x")

    ctx.contextualize(doc, [])

    assert (doc.metadata_ or {}).get("contextualization_version") is None


# ---------- NullChunkContextualizer ----------


def test_null_contextualizer_passthrough_and_stamps_distinct_version() -> None:
    """``null`` stamp lets future targeted re-embed distinguish 'never
    contextualized' from 'contextualized with v1/v2 prompt'."""
    null_ctx = NullChunkContextualizer()
    doc = _FakeDocument(metadata={"skills": ["stripe"]})

    chunks = [_chunk("a", 0), _chunk("b", 1)]
    out = null_ctx.contextualize(doc, chunks)

    assert out is chunks  # null is a no-op for chunks
    assert null_ctx.model_name == "none"
    assert doc.metadata_ is not None
    assert doc.metadata_.get("contextualization_version") == "null"
    # Pre-existing keys preserved.
    assert doc.metadata_.get("skills") == ["stripe"]
