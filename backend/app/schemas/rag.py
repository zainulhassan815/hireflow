"""RAG question-answering DTOs."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.errors import ErrorBody


class RagRequest(BaseModel):
    """Ask a question about uploaded documents."""

    question: str = Field(
        ...,
        min_length=1,
        description="Natural language question about document content",
        examples=["What skills does Alice have?"],
    )
    document_ids: list[UUID] | None = Field(
        None,
        description="Limit context to specific documents. None = search all.",
    )
    max_chunks: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum context chunks to retrieve for the answer",
    )


class SourceCitation(BaseModel):
    """A source chunk used to generate the answer."""

    document_id: UUID = Field(..., description="Source document ID")
    filename: str = Field(..., description="Source document filename")
    chunk_index: int = Field(..., description="Chunk position in the document")
    text: str = Field(..., description="Chunk text used as context")
    match_spans: list[tuple[int, int]] = Field(
        default_factory=list,
        description=(
            "Non-overlapping ``[start, end)`` character offsets within "
            "``text`` where question terms matched. Frontends render "
            "these as ``<mark>`` spans."
        ),
        examples=[[[0, 8]]],
    )


class RagResponse(BaseModel):
    """AI-generated answer with source citations."""

    answer: str = Field(..., description="Generated answer based on document context")
    citations: list[SourceCitation] = Field(
        ..., description="Document chunks used to generate the answer"
    )
    model: str = Field(
        ...,
        description="LLM model used for generation",
        examples=["claude-sonnet-4-5-20250514"],
    )
    query_time_ms: int = Field(
        ..., description="Total query + generation time in milliseconds"
    )
    confidence: Literal["high", "medium", "low"] | None = Field(
        None,
        description=(
            "Answer confidence band derived from top-chunk vector distance "
            "(F81.e). ``null`` when no answer was grounded in documents "
            "(empty retrieval → sentinel reply); the frontend should hide "
            "the badge in that case."
        ),
        examples=["high"],
    )


# --------------------------------------------------------------------------
# Streaming (SSE) events
#
# The wire format on ``POST /rag/stream`` is a sequence of Server-Sent
# Events. Each frame is one ``StreamEvent`` instance, serialized to JSON,
# with the SSE ``event:`` header echoing the discriminator so native
# ``EventSource`` consumers can register named listeners too.
#
# Order on a successful query:
#   citations  (fires once, before any delta)
#   delta      (fires many times, one per LLM text delta)
#   done       (fires once at the end, carries model + timing)
#
# If retrieval returns no hits: ``done`` fires alone (no citations, no
# deltas). If the LLM fails mid-stream: ``error`` fires and the stream
# closes.
# --------------------------------------------------------------------------


class StreamDone(BaseModel):
    """Final-event payload: model identifier and total elapsed time."""

    model: str = Field(
        ...,
        description="LLM model that produced the answer.",
        examples=["claude-sonnet-4-5-20250514"],
    )
    query_time_ms: int = Field(
        ..., description="Total query + generation time in milliseconds."
    )
    confidence: Literal["high", "medium", "low"] | None = Field(
        None,
        description=(
            "Answer confidence band (F81.e). ``null`` when no answer was "
            "grounded in documents (empty retrieval → sentinel)."
        ),
        examples=["high"],
    )


class CitationsEvent(BaseModel):
    """First event on the stream: the source chunks feeding the answer."""

    event: Literal["citations"] = "citations"
    data: list[SourceCitation]


class DeltaEvent(BaseModel):
    """A text delta from the model. Many of these per answer."""

    event: Literal["delta"] = "delta"
    data: str


class DoneEvent(BaseModel):
    """Terminal success event. Carries summary metadata."""

    event: Literal["done"] = "done"
    data: StreamDone


class ErrorEvent(BaseModel):
    """Terminal failure event. Reuses the project-wide error envelope."""

    event: Literal["error"] = "error"
    data: ErrorBody


StreamEvent = Annotated[
    CitationsEvent | DeltaEvent | DoneEvent | ErrorEvent,
    Field(discriminator="event"),
]
