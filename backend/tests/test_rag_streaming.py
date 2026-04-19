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
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from app.adapters.protocols import IntentResult, RetrievedChunk
from app.models import UserRole
from app.schemas.rag import CitationsEvent, DeltaEvent, DoneEvent, ErrorEvent
from app.services.rag_service import RagService

# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


class _FakeChunkRetriever:
    """Returns a canned list of ``RetrievedChunk``; no real retrieval.

    Replaces the F81.a-era ``_FakeVectorStore`` + ``_FakeDocumentRepo``
    pair. Under F81.k, ``RagService`` consumes ranked chunks directly —
    the retriever is the only retrieval collaborator the service sees.
    """

    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self._chunks = chunks
        self.calls: list[dict[str, Any]] = []

    async def retrieve_chunks(
        self,
        *,
        actor: Any,
        query: str,
        document_ids: list[UUID] | None,
        limit: int,
    ) -> list[RetrievedChunk]:
        self.calls.append(
            {
                "actor": actor,
                "query": query,
                "document_ids": document_ids,
                "limit": limit,
            }
        )
        if document_ids is None:
            return list(self._chunks)
        requested = set(document_ids)
        return [c for c in self._chunks if c.document_id in requested]


def _fake_user(*, role: UserRole = UserRole.HR) -> Any:
    """Minimal stand-in for ``app.models.User``.

    ``ChunkRetriever.retrieve_chunks`` only reads ``actor.id`` and
    ``actor.role`` in production; tests use fakes that expose just
    those attributes.
    """
    return MagicMock(id=uuid4(), role=role)


class _FakeIntentClassifier:
    """Returns a canned ``IntentResult``; no embedder required.

    Default tests use a ``"general"`` classifier so existing
    expectations (prose-style answers, default prompt) hold. Tests
    that exercise F81.g specifically pass a classifier that returns
    a non-default intent.
    """

    def __init__(
        self,
        intent: str = "general",
        confidence: float = 0.0,
        runner_up: str | None = None,
    ) -> None:
        self._result = IntentResult(
            intent=intent, confidence=confidence, runner_up=runner_up
        )
        self.calls: list[str] = []

    def classify(self, query: str) -> IntentResult:
        self.calls.append(query)
        return self._result


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


def _chunk(
    doc_id: UUID,
    *,
    chunk_index: int,
    text: str,
    filename: str = "doc.pdf",
    distance: float = 0.2,
    score: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> RetrievedChunk:
    meta = {"chunk_index": chunk_index}
    if metadata:
        meta.update(metadata)
    return RetrievedChunk(
        document_id=doc_id,
        filename=filename,
        chunk_index=chunk_index,
        text=text,
        distance=distance,
        score=score,
        metadata=meta,
    )


def _make_service(
    *,
    chunks: list[RetrievedChunk],
    llm: Any,
    classifier: _FakeIntentClassifier | None = None,
) -> tuple[RagService, _FakeChunkRetriever]:
    """Construct RagService backed by a fake chunk retriever.

    Returns the service plus the retriever so tests can inspect the
    retriever's recorded calls (e.g. to assert ``actor`` was threaded
    through or ``document_ids`` was forwarded).

    ``classifier`` defaults to a ``"general"`` classifier so existing
    tests (F81.a–k) see no behavior change. Tests that exercise F81.g
    pass a classifier returning a specific intent.
    """
    retriever = _FakeChunkRetriever(chunks)
    service = RagService(
        retriever=retriever,
        llm=llm,
        classifier=classifier or _FakeIntentClassifier(),
    )
    return service, retriever


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
    chunks = [
        _chunk(
            alice_id,
            chunk_index=0,
            filename="alice.pdf",
            text="Alice has 5 years of Kubernetes.",
        ),
        _chunk(bob_id, chunk_index=2, filename="bob.pdf", text="Bob worked at Google."),
    ]
    llm = _FakeStreamingLlm(["Alice ", "has ", "Kubernetes."])
    service, retriever = _make_service(chunks=chunks, llm=llm)

    events = [
        e async for e in service.stream_query(actor=_fake_user(), question="kubernetes")
    ]

    # 1 citations + 3 deltas + 1 done = 5 events
    assert len(events) == 5
    assert isinstance(events[0], CitationsEvent)
    assert {c.filename for c in events[0].data} == {"alice.pdf", "bob.pdf"}

    assert [type(e) for e in events[1:4]] == [DeltaEvent, DeltaEvent, DeltaEvent]
    assert "".join(e.data for e in events[1:4]) == "Alice has Kubernetes."

    assert isinstance(events[-1], DoneEvent)
    assert events[-1].data.model == "fake-llm-1"
    assert events[-1].data.query_time_ms >= 0

    # F81.k — actor is threaded through retrieval.
    assert len(retriever.calls) == 1
    assert retriever.calls[0]["query"] == "kubernetes"


# --------------------------------------------------------------------------
# No-hits fallback
# --------------------------------------------------------------------------


async def test_stream_query_with_no_hits_emits_fallback_delta_then_done() -> None:
    llm = _FakeStreamingLlm(["should not see me"])
    service, _ = _make_service(chunks=[], llm=llm)

    events = [
        e
        async for e in service.stream_query(
            actor=_fake_user(), question="unknown topic"
        )
    ]

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
    chunks = [
        _chunk(
            alice_id,
            chunk_index=0,
            filename="alice.pdf",
            text="Alice has 5 years of Kubernetes.",
        )
    ]
    llm = _MidStreamFailureLlm()
    service, _ = _make_service(chunks=chunks, llm=llm)

    events = [
        e async for e in service.stream_query(actor=_fake_user(), question="kubernetes")
    ]

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


async def test_system_prompt_carries_fallback_contract_and_evidence_rules() -> None:
    """Guard against silent regressions in the F81.d contract (now in
    F81.g's composed prompt stack).

    The exact fallback sentinel, inline-citation rule, and the default
    word cap for general prose all come from the ``general``-intent
    prompt composition. Each is checked here so an accidental edit to
    ``EVIDENCE_RULES`` / ``IDENTITY`` / ``FORMAT_RULES`` trips a test
    rather than silently regressing LLM behavior.
    """
    from app.services.rag_prompts import build_system_prompt

    prompt = build_system_prompt("general")

    # Exact fallback sentinel — frontend and eval harness both look
    # for this literal string.
    assert "Not in the provided documents." in prompt

    # Inline citation rule with the square-bracket filename example.
    assert "[alice_resume.pdf]" in prompt
    assert "square brackets" in prompt

    # Default word cap for the prose intent.
    assert "200 words" in prompt

    # Voice layer (identity) present.
    assert "HR research assistant" in prompt


async def test_build_context_includes_filename_per_chunk(alice_id: UUID) -> None:
    """The user prompt must expose each chunk's source filename so the
    inline-citation rule in the system prompt has something to read.
    """
    chunks = [
        _chunk(
            alice_id, chunk_index=3, filename="alice_resume.pdf", text="Alice loves Go."
        )
    ]
    llm = _FakeStreamingLlm(["ok"])
    service, _ = _make_service(chunks=chunks, llm=llm)

    ctx = await service._build_context(  # type: ignore[attr-defined]
        actor=_fake_user(),
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


def _chunk_at(
    doc_id: UUID,
    *,
    distance: float,
    text: str = "x",
    filename: str = "doc.pdf",
) -> RetrievedChunk:
    return _chunk(
        doc_id,
        chunk_index=0,
        text=text,
        filename=filename,
        distance=distance,
    )


async def test_distance_filter_drops_hits_above_cutoff(
    monkeypatch: pytest.MonkeyPatch, alice_id: UUID, bob_id: UUID
) -> None:
    """Chunks above the F81.b cutoff never reach the LLM or citations."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", 0.5)
    monkeypatch.setattr(settings, "rag_context_token_budget", 10_000)

    charlie_id = uuid4()
    chunks = [
        _chunk_at(alice_id, distance=0.1, filename="alice.pdf", text="Alice is kept."),
        _chunk_at(bob_id, distance=0.4, filename="bob.pdf", text="Bob is kept."),
        _chunk_at(
            charlie_id, distance=0.9, filename="charlie.pdf", text="Charlie is dropped."
        ),
    ]
    llm = _FakeStreamingLlm(["ok"])
    service, _ = _make_service(chunks=chunks, llm=llm)

    ctx = await service._build_context(  # type: ignore[attr-defined]
        actor=_fake_user(), question="q", document_ids=None, max_chunks=10
    )
    assert ctx is not None
    filenames = {c["filename"] for c in ctx.citations}
    assert filenames == {"alice.pdf", "bob.pdf"}
    # The filtered chunk's text must not reach the LLM either —
    # cosmetic-only filter would be a silent correctness bug.
    assert "Charlie is dropped." not in ctx.user_prompt


async def test_all_hits_above_cutoff_routes_through_no_hits_fallback(
    monkeypatch: pytest.MonkeyPatch, alice_id: UUID
) -> None:
    """Every chunk over the cutoff → sentinel fallback, no LLM call."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", 0.2)

    chunks = [
        _chunk_at(alice_id, distance=0.9, filename="alice.pdf", text="Off-topic.")
    ]
    llm = _FakeStreamingLlm(["should-not-see-me"])
    service, _ = _make_service(chunks=chunks, llm=llm)

    events = [
        e
        async for e in service.stream_query(
            actor=_fake_user(), question="quantum physics"
        )
    ]
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
    chunks = [
        _chunk_at(alice_id, distance=0.1, filename="a.pdf", text=chunk_text),
        _chunk_at(bob_id, distance=0.2, filename="b.pdf", text=chunk_text),
        _chunk_at(charlie_id, distance=0.3, filename="c.pdf", text=chunk_text),
        _chunk_at(dora_id, distance=0.4, filename="d.pdf", text=chunk_text),
        _chunk_at(eve_id, distance=0.5, filename="e.pdf", text=chunk_text),
    ]
    llm = _FakeStreamingLlm(["ok"])
    service, _ = _make_service(chunks=chunks, llm=llm)

    ctx = await service._build_context(  # type: ignore[attr-defined]
        actor=_fake_user(), question="q", document_ids=None, max_chunks=10
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
    chunks = [_chunk_at(alice_id, distance=0.1, filename="alice.pdf", text=huge)]
    llm = _FakeStreamingLlm(["ok"])
    service, _ = _make_service(chunks=chunks, llm=llm)

    with caplog.at_level("WARNING", logger="app.services.rag_service"):
        ctx = await service._build_context(  # type: ignore[attr-defined]
            actor=_fake_user(), question="q", document_ids=None, max_chunks=10
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
# F81.b cutoff after F81.k — now a tightening knob on top of the retriever
# --------------------------------------------------------------------------


async def test_f81b_cutoff_is_noop_when_setting_is_none(
    monkeypatch: pytest.MonkeyPatch, alice_id: UUID
) -> None:
    """When ``rag_context_max_distance`` is None, F81.b skips the
    distance filter entirely — the retriever already applied the
    search threshold, so filtering again at the same floor is a
    double-filter workaround we explicitly avoided."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", None)
    monkeypatch.setattr(settings, "rag_context_token_budget", 10_000)

    # A chunk that would fail ANY embedder threshold (distance 0.99)
    # still passes because F81.b short-circuits.
    chunks = [_chunk_at(alice_id, distance=0.99, filename="a.pdf", text="t")]
    service, _ = _make_service(chunks=chunks, llm=_FakeStreamingLlm(["ok"]))

    ctx = await service._build_context(  # type: ignore[attr-defined]
        actor=_fake_user(), question="q", document_ids=None, max_chunks=5
    )
    assert ctx is not None
    assert [c["filename"] for c in ctx.citations] == ["a.pdf"]


async def test_document_ids_forwarded_to_retriever(
    monkeypatch: pytest.MonkeyPatch, alice_id: UUID, bob_id: UUID
) -> None:
    """When the RAG request carries ``document_ids``, RagService
    passes the filter straight through to the retriever. The retriever
    is responsible for scoping at each retrieval source (F81.k)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", None)
    monkeypatch.setattr(settings, "rag_context_token_budget", 10_000)

    chunks = [
        _chunk_at(alice_id, distance=0.1, filename="a.pdf", text="alice"),
        _chunk_at(bob_id, distance=0.1, filename="b.pdf", text="bob"),
    ]
    service, retriever = _make_service(chunks=chunks, llm=_FakeStreamingLlm(["ok"]))

    ctx = await service._build_context(  # type: ignore[attr-defined]
        actor=_fake_user(),
        question="q",
        document_ids=[alice_id],
        max_chunks=5,
    )
    assert ctx is not None
    assert retriever.calls[-1]["document_ids"] == [alice_id]
    # The fake retriever already scopes; assert RagService trusts it.
    assert {c["filename"] for c in ctx.citations} == {"a.pdf"}


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

    chunks = [
        _chunk(
            alice_id,
            chunk_index=0,
            filename="alice.pdf",
            text="Alice has 5 years of Kubernetes.",
        )
    ]
    service, _ = _make_service(
        chunks=chunks,
        llm=_TypedFailureLlm(LlmRateLimited(retry_after_seconds=30)),
    )

    events = [e async for e in service.stream_query(actor=_fake_user(), question="q")]
    assert [type(e) for e in events] == [CitationsEvent, DeltaEvent, ErrorEvent]
    err = events[-1]
    assert isinstance(err, ErrorEvent)
    assert err.data.code == "llm_rate_limited"
    assert err.data.details == {"retry_after_seconds": 30}


async def test_timeout_emits_llm_timeout_code(alice_id: UUID) -> None:
    from app.domain.exceptions import LlmTimeout

    chunks = [
        _chunk(
            alice_id,
            chunk_index=0,
            filename="alice.pdf",
            text="Alice has 5 years of Kubernetes.",
        )
    ]
    service, _ = _make_service(chunks=chunks, llm=_TypedFailureLlm(LlmTimeout("slow")))

    events = [e async for e in service.stream_query(actor=_fake_user(), question="q")]
    err = events[-1]
    assert isinstance(err, ErrorEvent)
    assert err.data.code == "llm_timeout"
    # No details for plain timeouts — no retry hint to surface.
    assert err.data.details is None


async def test_unavailable_emits_llm_unavailable_code(alice_id: UUID) -> None:
    from app.domain.exceptions import LlmUnavailable

    chunks = [
        _chunk(
            alice_id,
            chunk_index=0,
            filename="alice.pdf",
            text="Alice has 5 years of Kubernetes.",
        )
    ]
    service, _ = _make_service(
        chunks=chunks, llm=_TypedFailureLlm(LlmUnavailable("network down"))
    )

    events = [e async for e in service.stream_query(actor=_fake_user(), question="q")]
    err = events[-1]
    assert isinstance(err, ErrorEvent)
    assert err.data.code == "llm_unavailable"


async def test_unknown_exception_still_falls_back_to_generic_llm_error(
    alice_id: UUID,
) -> None:
    """Regression guard: a genuinely unknown failure (not one of our
    domain subclasses) still routes to the generic ``llm_error``
    envelope rather than being mis-categorised."""
    chunks = [
        _chunk(
            alice_id,
            chunk_index=0,
            filename="alice.pdf",
            text="Alice has 5 years of Kubernetes.",
        )
    ]
    service, _ = _make_service(
        chunks=chunks, llm=_TypedFailureLlm(ValueError("completely unexpected"))
    )

    events = [e async for e in service.stream_query(actor=_fake_user(), question="q")]
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


# --------------------------------------------------------------------------
# F81.e — answer confidence indicator
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("top_distance", "expected"),
    [
        (0.05, "high"),
        (0.20, "high"),  # boundary
        (0.21, "medium"),
        (0.30, "medium"),  # boundary
        (0.31, "low"),
        (0.50, "low"),
    ],
)
def test_compute_confidence_bands(top_distance: float, expected: str) -> None:
    """Pure function — top-chunk distance maps to the band via the
    configured thresholds. Boundaries are inclusive on the lower side."""
    from app.services.rag_service import _compute_confidence

    chunk = _chunk_at(uuid4(), distance=top_distance, text="")
    assert _compute_confidence([chunk]) == expected


async def test_stream_done_carries_confidence_from_top_hit(
    monkeypatch: pytest.MonkeyPatch, alice_id: UUID
) -> None:
    """DoneEvent.data.confidence reflects the top (best) chunk's band,
    not a later chunk's. Guards against a future reorder swapping them."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", 0.9)
    monkeypatch.setattr(settings, "rag_context_token_budget", 10_000)

    # Top chunk at 0.15 → "high"; second chunk (weaker) at 0.28 would
    # be "medium". Confidence must follow the top, not the bottom.
    bob_id = uuid4()
    chunks = [
        _chunk_at(
            alice_id,
            distance=0.15,
            filename="alice.pdf",
            text="Alice is a strong match.",
        ),
        _chunk_at(
            bob_id, distance=0.28, filename="bob.pdf", text="Bob is a weaker match."
        ),
    ]
    service, _ = _make_service(chunks=chunks, llm=_FakeStreamingLlm(["ok"]))

    events = [e async for e in service.stream_query(actor=_fake_user(), question="q")]
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.data.confidence == "high"


async def test_stream_done_confidence_is_none_on_no_hits_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty retrieval → no answer to rate → confidence is null.
    Distinguishing absence from 'low' on the wire lets the frontend
    hide the badge rather than render a red one."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", 0.9)

    service, _ = _make_service(chunks=[], llm=_FakeStreamingLlm(["unused"]))

    events = [e async for e in service.stream_query(actor=_fake_user(), question="q")]
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.data.confidence is None


async def test_sync_query_result_carries_confidence(
    monkeypatch: pytest.MonkeyPatch, alice_id: UUID
) -> None:
    """Regression guard: the sync path consumes the same _RagContext,
    so confidence travels unchanged. Asserted directly so a future
    change that bypasses _build_context in the sync branch trips here."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_context_max_distance", 0.9)
    monkeypatch.setattr(settings, "rag_context_token_budget", 10_000)

    chunks = [
        _chunk_at(
            alice_id,
            distance=0.10,
            filename="alice.pdf",
            text="Alice is a perfect match.",
        )
    ]
    service, _ = _make_service(chunks=chunks, llm=_FakeStreamingLlm(["the answer"]))

    result = await service.query(actor=_fake_user(), question="q")
    assert result.confidence == "high"


async def test_sync_query_confidence_is_none_on_fallback() -> None:
    """Sync-path fallback also carries None confidence."""
    service, _ = _make_service(chunks=[], llm=_FakeStreamingLlm(["unused"]))

    result = await service.query(actor=_fake_user(), question="quantum physics")
    assert result.confidence is None
    assert result.answer == "Not in the provided documents."


# --------------------------------------------------------------------------
# F81.h — section_heading + page_number travel onto citations
# --------------------------------------------------------------------------


async def test_section_heading_and_page_number_travel_onto_citation(
    alice_id: UUID,
) -> None:
    """F82.e stamps ``section_heading`` on chunk metadata; F81.h surfaces
    it on SourceCitation so the frontend can render the section label."""
    chunks = [
        _chunk(
            alice_id,
            chunk_index=0,
            filename="alice.pdf",
            text="Alice has Kubernetes experience since 2019.",
            distance=0.1,
            metadata={"section_heading": "Experience", "page_number": 2},
        )
    ]
    service, _ = _make_service(chunks=chunks, llm=_FakeStreamingLlm(["ok"]))

    ctx = await service._build_context(  # type: ignore[attr-defined]
        actor=_fake_user(), question="q", document_ids=None, max_chunks=5
    )
    assert ctx is not None
    assert ctx.citations[0]["section_heading"] == "Experience"
    assert ctx.citations[0]["page_number"] == 2


async def test_missing_section_heading_renders_as_none(alice_id: UUID) -> None:
    """When the extractor didn't surface a heading (e.g. raw text doc),
    the citation carries ``section_heading=None`` — the frontend
    conditionally hides the section label in that case."""
    chunks = [
        _chunk(
            alice_id,
            chunk_index=0,
            filename="alice.pdf",
            text="plain text, no heading",
            distance=0.1,
        )
    ]
    service, _ = _make_service(chunks=chunks, llm=_FakeStreamingLlm(["ok"]))

    ctx = await service._build_context(  # type: ignore[attr-defined]
        actor=_fake_user(), question="q", document_ids=None, max_chunks=5
    )
    assert ctx is not None
    assert ctx.citations[0]["section_heading"] is None
    assert ctx.citations[0]["page_number"] is None


# --------------------------------------------------------------------------
# F81.g — classifier output travels to RagResult + DoneEvent + user prompt
# --------------------------------------------------------------------------


async def test_classified_intent_travels_onto_done_event(
    alice_id: UUID,
) -> None:
    """The classifier's result must reach ``DoneEvent.data.intent`` so
    the frontend can react to the answer shape. This test locks in
    the wire contract — changing either the event schema or the
    threading in ``stream_query`` would trip it."""
    chunks = [_chunk(alice_id, chunk_index=0, filename="a.pdf", text="x")]
    classifier = _FakeIntentClassifier(
        intent="comparison", confidence=0.82, runner_up="ranking"
    )
    service, _ = _make_service(
        chunks=chunks, llm=_FakeStreamingLlm(["ok"]), classifier=classifier
    )

    events = [e async for e in service.stream_query(actor=_fake_user(), question="q")]
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.data.intent == "comparison"
    assert done.data.intent_confidence == pytest.approx(0.82)

    # Classifier was invoked with the user's query.
    assert classifier.calls == ["q"]


async def test_sync_query_result_carries_intent(alice_id: UUID) -> None:
    """Parallel assertion for the sync path — same contract, different
    return shape."""
    chunks = [_chunk(alice_id, chunk_index=0, filename="a.pdf", text="x")]
    classifier = _FakeIntentClassifier(intent="count", confidence=0.65)
    service, _ = _make_service(
        chunks=chunks, llm=_FakeStreamingLlm(["ok"]), classifier=classifier
    )

    result = await service.query(actor=_fake_user(), question="q")
    assert result.intent == "count"
    assert result.intent_confidence == pytest.approx(0.65)


async def test_intent_format_instructions_reach_the_system_prompt(
    alice_id: UUID,
) -> None:
    """When intent is ``count``, the LLM must receive the
    count-specific format directive. Without this end-to-end plumbing,
    structured answers never materialize — the classifier would be
    observability-only."""
    chunks = [_chunk(alice_id, chunk_index=0, filename="a.pdf", text="x")]
    llm = _FakeStreamingLlm(["ok"])
    classifier = _FakeIntentClassifier(intent="count", confidence=0.9)
    service, _ = _make_service(chunks=chunks, llm=llm, classifier=classifier)

    ctx = await service._build_context(  # type: ignore[attr-defined]
        actor=_fake_user(), question="how many", document_ids=None, max_chunks=5
    )
    assert ctx is not None
    # Count intent's format directive: number alone + bullets.
    assert "number alone on its own line" in ctx.system_prompt
    # Voice layer still present — prompt composition didn't lose it.
    assert "HR research assistant" in ctx.system_prompt


async def test_fallback_intent_still_carries_general_on_wire(
    alice_id: UUID,
) -> None:
    """Default classifier output (``general``) is valid and the wire
    should carry it explicitly — never ``null`` or missing, so the
    frontend has a consistent field to switch on."""
    chunks = [_chunk(alice_id, chunk_index=0, filename="a.pdf", text="x")]
    service, _ = _make_service(chunks=chunks, llm=_FakeStreamingLlm(["ok"]))

    events = [e async for e in service.stream_query(actor=_fake_user(), question="q")]
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.data.intent == "general"
    assert done.data.intent_confidence == 0.0
