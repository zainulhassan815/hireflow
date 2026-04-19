"""RAG question-answering endpoints."""

from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, RagServiceDep
from app.domain.exceptions import ServiceUnavailable
from app.schemas.errors import ErrorResponse
from app.schemas.rag import (
    CitationsEvent,
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    RagRequest,
    RagResponse,
    SourceCitation,
)

_RagStreamEvent = CitationsEvent | DeltaEvent | DoneEvent | ErrorEvent

router = APIRouter()


@router.post(
    "/query",
    response_model=RagResponse,
    summary="Ask a question about documents",
    description=(
        "Retrieval-Augmented Generation: finds the most relevant document "
        "chunks via vector search, builds a context window, and sends the "
        "question to the configured LLM (Claude or Ollama). Returns the "
        "generated answer with source citations pointing to the exact "
        "chunks used. Requires both ChromaDB and an LLM provider to be "
        "configured."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        503: {
            "model": ErrorResponse,
            "description": "RAG not available (ChromaDB or LLM not configured)",
        },
    },
)
async def query_documents(
    request: RagRequest,
    current_user: CurrentUser,
    rag: RagServiceDep,
) -> RagResponse:
    if rag is None:
        raise ServiceUnavailable(
            "RAG is not available. Configure an LLM provider "
            "(ANTHROPIC_API_KEY or Ollama) and ensure ChromaDB is running."
        )

    result = await rag.query(
        question=request.question,
        document_ids=request.document_ids,
        max_chunks=request.max_chunks,
    )
    return RagResponse(
        answer=result.answer,
        citations=[SourceCitation(**c) for c in result.citations],
        model=result.model,
        query_time_ms=result.query_time_ms,
        confidence=result.confidence,
    )


@router.post(
    "/stream",
    summary="Ask a question about documents (streaming)",
    description=(
        "Same request shape as `POST /rag/query`, but returns a "
        "Server-Sent Events stream (`text/event-stream`) so tokens "
        "appear in the UI as the model generates them. Events:\n\n"
        "- `citations` (fires first) — source chunks feeding the answer. "
        "Omitted when retrieval returned no hits.\n"
        "- `delta` (fires 0..N times) — one text delta from the model.\n"
        "- `done` (terminal on success) — LLM model name + total elapsed ms.\n"
        "- `error` (terminal on failure) — standard `ErrorBody` envelope.\n\n"
        "Each SSE frame carries the event type in both the `event:` "
        "header and inside the JSON payload's `event` field, so "
        "consumers may switch on either. Browsers need a `fetch`-based "
        "reader (the native `EventSource` API is GET-only and cannot "
        "carry an `Authorization` header); the project's "
        "`src/api/rag-stream.ts` is a ~30-line example."
    ),
    responses={
        200: {
            "description": "SSE stream of RAG events (see description).",
            "content": {"text/event-stream": {}},
        },
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        503: {
            "model": ErrorResponse,
            "description": "RAG not available (ChromaDB or LLM not configured)",
        },
    },
)
async def stream_answer(
    request: RagRequest,
    current_user: CurrentUser,
    rag: RagServiceDep,
) -> StreamingResponse:
    if rag is None:
        # Raised before opening the stream — client gets a plain 503
        # with the standard ErrorResponse envelope, matching /rag/query.
        raise ServiceUnavailable(
            "RAG is not available. Configure an LLM provider "
            "(ANTHROPIC_API_KEY or Ollama) and ensure ChromaDB is running."
        )

    async def encoded_events() -> AsyncIterator[str]:
        async for event in rag.stream_query(
            question=request.question,
            document_ids=request.document_ids,
            max_chunks=request.max_chunks,
        ):
            yield _sse_frame(event)

    return StreamingResponse(
        encoded_events(),
        media_type="text/event-stream",
        headers={
            # Tell Nginx (and well-behaved upstream proxies) not to
            # buffer the response. Without this, intermediaries hold
            # bytes until the connection closes and streaming is
            # defeated. Caddy doesn't buffer SSE by default; harmless
            # there.
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )


def _sse_frame(event: _RagStreamEvent) -> str:
    """Serialize one Pydantic event as an SSE frame.

    The event object's ``event`` discriminator is echoed into the SSE
    ``event:`` header (so a native ``EventSource`` consumer could
    register named listeners if we ever needed one) AND lives inside
    the JSON ``data:`` payload (so a single ``onmessage`` handler can
    switch on it without reading two properties). The ~10 bytes of
    redundancy buys full dual compatibility.
    """
    return f"event: {event.event}\ndata: {event.model_dump_json()}\n\n"
