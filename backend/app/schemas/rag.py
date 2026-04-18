"""RAG question-answering DTOs."""

from uuid import UUID

from pydantic import BaseModel, Field


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
