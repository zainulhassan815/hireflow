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


class _FakeEmbedder:
    """Minimal embedder stub — only the RAG-cutoff property is exercised.

    Matches the production path where ``RagService._resolve_distance_cutoff``
    reads ``vector_store.embedder.recommended_distance_threshold``.
    """

    def __init__(self, threshold: float = 0.5) -> None:
        self._threshold = threshold

    @property
    def recommended_distance_threshold(self) -> float:
        return self._threshold


class _FakeVectorStore:
    """Returns a canned list of ``VectorHit``; no real Chroma.

    Carries an ``embedder`` attribute mirroring ``ChromaVectorStore``,
    so the distance-cutoff resolution path is exercised end-to-end.
    """

    def __init__(
        self,
        hits: list[VectorHit],
        *,
        embedder: _FakeEmbedder | None = None,
    ) -> None:
        self._hits = hits
        self.query_calls: list[dict[str, Any]] = []
        self.embedder = embedder or _FakeEmbedder()

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


class _TypedFailureLlm:
    """Yields one delta, then raises a specific domain exception.

    Used to assert that ``stream_query`` dispatches each
    ``LlmProviderError`` subclass into the right ``ErrorEvent`` shape
    (code + details) without reverting to the generic fallback.
    """

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def complete(self, system: str, user: str) -> str:
        raise self._exc

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        yield "partial "
        raise self._exc

    @property
    def model_name(self) -> str:
        return "fake-llm-typed"


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


# --------------------------------------------------------------------------
# F81.b — distance filter
# --------------------------------------------------------------------------


def _hit_at(doc_id: UUID, *, distance: float, text: str = "x") -> VectorHit:
    return VectorHit(
        chunk_id=f"{doc_id}-{distance}",
        document_id=str(doc_id),
        text=text,
        metadata={"chunk_index": 0},
        distance=distance,
    )


async def test_distance_filter_drops_hits_above_cutoff(
    monkeypatch: pytest.MonkeyPatch, alice_id: UUID, bob_id: UUID
) -> None:
    """Hits above the distance cutoff never reach the LLM or the
    citations list. Below-cutoff hits do."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", 0.5)
    monkeypatch.setattr(settings, "rag_context_token_budget", 10_000)

    charlie_id = uuid4()
    hits = [
        _hit_at(alice_id, distance=0.1, text="Alice is kept."),
        _hit_at(bob_id, distance=0.4, text="Bob is kept."),
        _hit_at(charlie_id, distance=0.9, text="Charlie is dropped."),
    ]
    vector_store = _FakeVectorStore(hits)
    docs = _FakeDocumentRepo(
        {alice_id: "alice.pdf", bob_id: "bob.pdf", charlie_id: "charlie.pdf"}
    )
    llm = _FakeStreamingLlm(["ok"])
    service = _make_service(docs=docs, vector_store=vector_store, llm=llm)

    ctx = await service._build_context(  # type: ignore[attr-defined]
        question="q", document_ids=None, max_chunks=10
    )
    assert ctx is not None
    filenames = {c["filename"] for c in ctx.citations}
    assert filenames == {"alice.pdf", "bob.pdf"}
    # Context that would be handed to the LLM must also not mention
    # the filtered chunk — otherwise the filter is only cosmetic.
    assert "Charlie is dropped." not in ctx.user_prompt


async def test_all_hits_above_cutoff_routes_through_no_hits_fallback(
    monkeypatch: pytest.MonkeyPatch, alice_id: UUID
) -> None:
    """When every hit is over the cutoff, stream_query falls back to
    the synthetic-delta sentinel path without touching the LLM.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", 0.2)

    hits = [_hit_at(alice_id, distance=0.9, text="Off-topic.")]
    vector_store = _FakeVectorStore(hits)
    docs = _FakeDocumentRepo({alice_id: "alice.pdf"})
    llm = _FakeStreamingLlm(["should-not-see-me"])
    service = _make_service(docs=docs, vector_store=vector_store, llm=llm)

    events = [e async for e in service.stream_query(question="quantum physics")]
    assert [type(e) for e in events] == [DeltaEvent, DoneEvent]
    assert events[0].data == "Not in the provided documents."
    assert llm.stream_calls == []


# --------------------------------------------------------------------------
# F81.c — token budget
# --------------------------------------------------------------------------


async def test_token_budget_truncates_trailing_chunks(
    monkeypatch: pytest.MonkeyPatch, alice_id: UUID, bob_id: UUID
) -> None:
    """With enough chunks to exceed the budget, only the leading
    chunks that fit are kept. 4 chars ≈ 1 token: a 1200-char chunk
    ≈ 300 tokens; 5 of them ≈ 1500 tokens. Budget 1000 keeps 3."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", 0.9)
    monkeypatch.setattr(settings, "rag_context_token_budget", 1000)

    chunk_text = "x" * 1200  # ~300 tokens
    charlie_id = uuid4()
    dora_id = uuid4()
    eve_id = uuid4()
    hits = [
        _hit_at(alice_id, distance=0.1, text=chunk_text),
        _hit_at(bob_id, distance=0.2, text=chunk_text),
        _hit_at(charlie_id, distance=0.3, text=chunk_text),
        _hit_at(dora_id, distance=0.4, text=chunk_text),
        _hit_at(eve_id, distance=0.5, text=chunk_text),
    ]
    vector_store = _FakeVectorStore(hits)
    docs = _FakeDocumentRepo(
        {
            alice_id: "a.pdf",
            bob_id: "b.pdf",
            charlie_id: "c.pdf",
            dora_id: "d.pdf",
            eve_id: "e.pdf",
        }
    )
    llm = _FakeStreamingLlm(["ok"])
    service = _make_service(docs=docs, vector_store=vector_store, llm=llm)

    ctx = await service._build_context(  # type: ignore[attr-defined]
        question="q", document_ids=None, max_chunks=10
    )
    assert ctx is not None
    filenames = [c["filename"] for c in ctx.citations]
    # First three fit (3 × 300 = 900 < 1000); fourth would push to
    # 1200 > 1000 and is dropped along with the rest.
    assert filenames == ["a.pdf", "b.pdf", "c.pdf"]


async def test_single_oversized_chunk_kept_with_warn(
    monkeypatch: pytest.MonkeyPatch,
    alice_id: UUID,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A top chunk larger than the whole budget is still included —
    answering from one oversized chunk beats refusing on a config
    technicality. A WARN log flags the anomaly for operators."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", 0.9)
    monkeypatch.setattr(settings, "rag_context_token_budget", 100)

    huge = "x" * 6000  # ~1500 tokens, far over the 100 budget
    hits = [_hit_at(alice_id, distance=0.1, text=huge)]
    vector_store = _FakeVectorStore(hits)
    docs = _FakeDocumentRepo({alice_id: "alice.pdf"})
    llm = _FakeStreamingLlm(["ok"])
    service = _make_service(docs=docs, vector_store=vector_store, llm=llm)

    with caplog.at_level("WARNING", logger="app.services.rag_service"):
        ctx = await service._build_context(  # type: ignore[attr-defined]
            question="q", document_ids=None, max_chunks=10
        )
    assert ctx is not None
    assert [c["filename"] for c in ctx.citations] == ["alice.pdf"]
    assert any(
        "exceeds budget" in record.message and record.levelname == "WARNING"
        for record in caplog.records
    )


def test_estimate_tokens_is_ceil_four_chars_per_token() -> None:
    """Sanity check on the heuristic. Off-by-one here would silently
    blow the budget on long documents."""
    from app.services.rag_service import _estimate_tokens

    assert _estimate_tokens("") == 0
    assert _estimate_tokens("x") == 1
    assert _estimate_tokens("x" * 4) == 1
    assert _estimate_tokens("x" * 5) == 2  # ceil, not floor
    assert _estimate_tokens("x" * 1000) == 250


# --------------------------------------------------------------------------
# Distance-cutoff resolution path (mirrors SearchService)
# --------------------------------------------------------------------------


async def test_distance_cutoff_prefers_explicit_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit config value overrides the embedder recommendation."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", 0.12)
    vector_store = _FakeVectorStore([], embedder=_FakeEmbedder(threshold=0.99))
    service = _make_service(
        docs=_FakeDocumentRepo({}),
        vector_store=vector_store,
        llm=_FakeStreamingLlm([]),
    )
    assert service._resolve_distance_cutoff() == 0.12  # type: ignore[attr-defined]


async def test_distance_cutoff_falls_back_to_embedder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No explicit setting → the embedder's recommendation travels
    automatically. F85.d relies on this for per-model thresholds."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", None)
    vector_store = _FakeVectorStore([], embedder=_FakeEmbedder(threshold=0.33))
    service = _make_service(
        docs=_FakeDocumentRepo({}),
        vector_store=vector_store,
        llm=_FakeStreamingLlm([]),
    )
    assert service._resolve_distance_cutoff() == 0.33  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
# F81.i — typed LLM-error dispatch in stream_query
# --------------------------------------------------------------------------


async def test_rate_limit_emits_typed_error_event_with_retry_after(
    alice_id: UUID,
) -> None:
    """LlmRateLimited → ErrorEvent carries ``llm_rate_limited`` code
    plus ``retry_after_seconds`` in ``details``. Drives F92.11's
    countdown UX; frontend switches on the code."""
    from app.domain.exceptions import LlmRateLimited

    hits = [_hit(alice_id, chunk_index=0, text="Alice has 5 years of Kubernetes.")]
    service = _make_service(
        docs=_FakeDocumentRepo({alice_id: "alice.pdf"}),
        vector_store=_FakeVectorStore(hits),
        llm=_TypedFailureLlm(LlmRateLimited(retry_after_seconds=30)),
    )

    events = [e async for e in service.stream_query(question="q")]
    assert [type(e) for e in events] == [CitationsEvent, DeltaEvent, ErrorEvent]
    err = events[-1]
    assert isinstance(err, ErrorEvent)
    assert err.data.code == "llm_rate_limited"
    assert err.data.details == {"retry_after_seconds": 30}


async def test_timeout_emits_llm_timeout_code(alice_id: UUID) -> None:
    from app.domain.exceptions import LlmTimeout

    hits = [_hit(alice_id, chunk_index=0, text="Alice has 5 years of Kubernetes.")]
    service = _make_service(
        docs=_FakeDocumentRepo({alice_id: "alice.pdf"}),
        vector_store=_FakeVectorStore(hits),
        llm=_TypedFailureLlm(LlmTimeout("slow")),
    )

    events = [e async for e in service.stream_query(question="q")]
    err = events[-1]
    assert isinstance(err, ErrorEvent)
    assert err.data.code == "llm_timeout"
    # No details for plain timeouts — no retry hint to surface.
    assert err.data.details is None


async def test_unavailable_emits_llm_unavailable_code(alice_id: UUID) -> None:
    from app.domain.exceptions import LlmUnavailable

    hits = [_hit(alice_id, chunk_index=0, text="Alice has 5 years of Kubernetes.")]
    service = _make_service(
        docs=_FakeDocumentRepo({alice_id: "alice.pdf"}),
        vector_store=_FakeVectorStore(hits),
        llm=_TypedFailureLlm(LlmUnavailable("network down")),
    )

    events = [e async for e in service.stream_query(question="q")]
    err = events[-1]
    assert isinstance(err, ErrorEvent)
    assert err.data.code == "llm_unavailable"


async def test_unknown_exception_still_falls_back_to_generic_llm_error(
    alice_id: UUID,
) -> None:
    """Regression guard: a genuinely unknown failure (not one of our
    domain subclasses) still routes to the generic ``llm_error``
    envelope rather than being mis-categorised."""
    hits = [_hit(alice_id, chunk_index=0, text="Alice has 5 years of Kubernetes.")]
    service = _make_service(
        docs=_FakeDocumentRepo({alice_id: "alice.pdf"}),
        vector_store=_FakeVectorStore(hits),
        llm=_TypedFailureLlm(ValueError("completely unexpected")),
    )

    events = [e async for e in service.stream_query(question="q")]
    err = events[-1]
    assert isinstance(err, ErrorEvent)
    assert err.data.code == "llm_error"
    # Exception message must NOT leak into user-visible field.
    assert "completely unexpected" not in err.data.message


# --------------------------------------------------------------------------
# F81.i — HTTP status mapping through the error handler
# --------------------------------------------------------------------------


async def test_llm_unavailable_returns_503_with_envelope() -> None:
    from fastapi import Request
    from fastapi.responses import JSONResponse

    from app.api.error_handlers import handle_domain_error
    from app.domain.exceptions import LlmUnavailable

    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    response = await handle_domain_error(request, LlmUnavailable("down"))
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    import json as _json

    body = _json.loads(response.body)
    assert body["error"]["code"] == "llm_unavailable"


async def test_llm_rate_limited_returns_429_with_details() -> None:
    from fastapi import Request

    from app.api.error_handlers import handle_domain_error
    from app.domain.exceptions import LlmRateLimited

    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    response = await handle_domain_error(
        request, LlmRateLimited(retry_after_seconds=12)
    )
    assert response.status_code == 429
    import json as _json

    body = _json.loads(response.body)
    assert body["error"]["code"] == "llm_rate_limited"
    assert body["error"]["details"] == {"retry_after_seconds": 12}


async def test_llm_timeout_returns_504() -> None:
    from fastapi import Request

    from app.api.error_handlers import handle_domain_error
    from app.domain.exceptions import LlmTimeout

    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    response = await handle_domain_error(request, LlmTimeout("slow"))
    assert response.status_code == 504
