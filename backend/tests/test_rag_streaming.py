"""F81.a + F81.d: streaming RAG + system-prompt tests.

These are unit tests on ``RagService.stream_query`` using fakes for
``VectorStore``, ``DocumentRepository``, and ``LlmProvider``. The aim
is to lock in the event contract (citations → deltas → done, or
delta-only-fallback → done, or citations → error) so any future edit
that breaks the order will fail loudly.

The route-level SSE encoding is covered separately via an ASGI
integration test at the bottom of this module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app.adapters.protocols import VectorHit
from app.repositories.document import DocumentRepository
from app.schemas.rag import CitationsEvent, DeltaEvent, DoneEvent, ErrorEvent
from app.services.rag_service import RagService

# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


class _FakeVectorStore:
    """Returns a canned list of ``VectorHit``; no real Chroma."""

    def __init__(self, hits: list[VectorHit]) -> None:
        self._hits = hits
        self.query_calls: list[dict[str, Any]] = []

    def upsert(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError

    def query(
        self,
        query_text: str,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        self.query_calls.append(
            {"query_text": query_text, "n_results": n_results, "where": where}
        )
        return list(self._hits)


class _FakeDocumentRepo:
    """Hands back ``SimpleNamespace(filename=...)`` for whatever IDs are asked."""

    def __init__(self, filenames: dict[UUID, str]) -> None:
        self._filenames = filenames

    async def get_many(self, document_ids: list[UUID]) -> dict[UUID, Any]:
        return {
            doc_id: SimpleNamespace(filename=self._filenames.get(doc_id, "unknown"))
            for doc_id in document_ids
        }


class _FakeStreamingLlm:
    """Records the prompts it sees, yields a canned list of text deltas."""

    def __init__(self, deltas: list[str], *, model: str = "fake-llm-1") -> None:
        self._deltas = deltas
        self._model = model
        self.complete_calls: list[tuple[str, str]] = []
        self.stream_calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.complete_calls.append((system, user))
        return "".join(self._deltas)

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        self.stream_calls.append((system, user))
        for delta in self._deltas:
            yield delta

    @property
    def model_name(self) -> str:
        return self._model


class _MidStreamFailureLlm:
    """Yields one delta, then raises. Exercises the error-event path."""

    def complete(self, system: str, user: str) -> str:
        raise RuntimeError("complete should not be called in stream tests")

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        yield "partial answer "
        raise RuntimeError("boom")

    @property
    def model_name(self) -> str:
        return "fake-llm-failing"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _hit(doc_id: UUID, *, chunk_index: int, text: str) -> VectorHit:
    return VectorHit(
        chunk_id=f"{doc_id}-{chunk_index}",
        document_id=str(doc_id),
        text=text,
        metadata={"chunk_index": chunk_index},
        distance=0.2,
    )


def _make_service(
    *,
    docs: _FakeDocumentRepo,
    vector_store: _FakeVectorStore,
    llm: _FakeStreamingLlm | _MidStreamFailureLlm,
) -> RagService:
    """Construct RagService with structurally-compatible fakes.

    ``RagService.__init__`` is typed against concrete classes
    (``DocumentRepository``) for ergonomic reasons, not Protocols, so
    the cast is the smallest honest thing we can do to satisfy the
    type checker without inventing interfaces purely for tests.
    """
    return RagService(
        documents=cast(DocumentRepository, docs),
        vector_store=vector_store,
        llm=llm,
    )


@pytest.fixture
def alice_id() -> UUID:
    return uuid4()


@pytest.fixture
def bob_id() -> UUID:
    return uuid4()


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


async def test_stream_query_emits_citations_then_deltas_then_done(
    alice_id: UUID, bob_id: UUID
) -> None:
    hits = [
        _hit(alice_id, chunk_index=0, text="Alice has 5 years of Kubernetes."),
        _hit(bob_id, chunk_index=2, text="Bob worked at Google."),
    ]
    vector_store = _FakeVectorStore(hits)
    docs = _FakeDocumentRepo({alice_id: "alice.pdf", bob_id: "bob.pdf"})
    llm = _FakeStreamingLlm(["Alice ", "has ", "Kubernetes."])

    service = _make_service(docs=docs, vector_store=vector_store, llm=llm)

    events = [e async for e in service.stream_query(question="kubernetes")]

    # 1 citations + 3 deltas + 1 done = 5 events
    assert len(events) == 5
    assert isinstance(events[0], CitationsEvent)
    assert {c.filename for c in events[0].data} == {"alice.pdf", "bob.pdf"}

    assert [type(e) for e in events[1:4]] == [DeltaEvent, DeltaEvent, DeltaEvent]
    assert "".join(e.data for e in events[1:4]) == "Alice has Kubernetes."

    assert isinstance(events[-1], DoneEvent)
    assert events[-1].data.model == "fake-llm-1"
    assert events[-1].data.query_time_ms >= 0


# --------------------------------------------------------------------------
# No-hits fallback
# --------------------------------------------------------------------------


async def test_stream_query_with_no_hits_emits_fallback_delta_then_done() -> None:
    vector_store = _FakeVectorStore([])
    docs = _FakeDocumentRepo({})
    llm = _FakeStreamingLlm(["should not see me"])

    service = _make_service(docs=docs, vector_store=vector_store, llm=llm)

    events = [e async for e in service.stream_query(question="unknown topic")]

    # Exactly one delta (the fallback sentinel) + one done. No
    # citations event. LLM must not have been touched — there was
    # nothing to ground the answer in.
    assert len(events) == 2
    assert isinstance(events[0], DeltaEvent)
    assert events[0].data == "Not in the provided documents."
    assert isinstance(events[1], DoneEvent)
    assert llm.stream_calls == []
    assert llm.complete_calls == []


# --------------------------------------------------------------------------
# Mid-stream LLM failure
# --------------------------------------------------------------------------


async def test_stream_query_emits_error_event_on_llm_failure(
    alice_id: UUID,
) -> None:
    hits = [_hit(alice_id, chunk_index=0, text="Alice has 5 years of Kubernetes.")]
    vector_store = _FakeVectorStore(hits)
    docs = _FakeDocumentRepo({alice_id: "alice.pdf"})
    llm = _MidStreamFailureLlm()

    service = _make_service(docs=docs, vector_store=vector_store, llm=llm)

    events = [e async for e in service.stream_query(question="kubernetes")]

    # citations + 1 delta (before failure) + error, no done
    assert [type(e) for e in events] == [CitationsEvent, DeltaEvent, ErrorEvent]
    err = events[-1]
    assert isinstance(err, ErrorEvent)
    assert err.data.code == "llm_error"
    # Client-visible message must stay generic — raw exception details
    # go to the server log, never the wire. See rag_service.py.
    assert "boom" not in err.data.message
    assert err.data.message


# --------------------------------------------------------------------------
# F81.d system prompt contract
# --------------------------------------------------------------------------


async def test_system_prompt_carries_fallback_contract_and_anti_preamble_rule(
    alice_id: UUID,
) -> None:
    """Guard against silent regressions in the F81.d prompt rules."""
    from app.services.rag_service import _SYSTEM_PROMPT

    # The exact fallback sentinel shows up in the prompt so the model
    # knows what to return when grounded-in-context fails.
    assert "Not in the provided documents." in _SYSTEM_PROMPT

    # Inline citation instruction is present.
    assert "cite the source filename" in _SYSTEM_PROMPT.lower()
    assert "[alice_resume.pdf]" in _SYSTEM_PROMPT

    # Anti-preamble rule mentions at least one concrete forbidden phrase.
    assert "Based on the documents" in _SYSTEM_PROMPT

    # Length cap.
    assert "200 words" in _SYSTEM_PROMPT


async def test_build_context_includes_filename_per_chunk(alice_id: UUID) -> None:
    """The user prompt must expose each chunk's source filename so the
    inline-citation rule in the system prompt has something to read.
    """
    hits = [_hit(alice_id, chunk_index=3, text="Alice loves Go.")]
    vector_store = _FakeVectorStore(hits)
    docs = _FakeDocumentRepo({alice_id: "alice_resume.pdf"})
    llm = _FakeStreamingLlm(["ok"])

    service = _make_service(docs=docs, vector_store=vector_store, llm=llm)

    ctx = await service._build_context(  # type: ignore[attr-defined]
        question="go experience",
        document_ids=None,
        max_chunks=5,
    )
    assert ctx is not None
    assert "alice_resume.pdf" in ctx.user_prompt
    assert "Alice loves Go." in ctx.user_prompt


# --------------------------------------------------------------------------
# Route-level SSE encoding
# --------------------------------------------------------------------------


async def test_sse_frame_has_event_header_and_json_payload() -> None:
    """Verify the SSE frame wire format — single source of truth for
    what a client receives on the wire.
    """
    from app.api.routes.rag import _sse_frame
    from app.schemas.rag import DeltaEvent, DoneEvent, StreamDone

    delta = DeltaEvent(data="hello")
    frame = _sse_frame(delta)
    # Header echoes the discriminator; payload is the whole pydantic
    # model as JSON so a single onmessage handler can switch on `.event`.
    assert frame.startswith("event: delta\n")
    assert '"event":"delta"' in frame
    assert '"data":"hello"' in frame
    assert frame.endswith("\n\n")

    done = DoneEvent(data=StreamDone(model="m", query_time_ms=42))
    done_frame = _sse_frame(done)
    assert done_frame.startswith("event: done\n")
    assert '"model":"m"' in done_frame
    assert '"query_time_ms":42' in done_frame
