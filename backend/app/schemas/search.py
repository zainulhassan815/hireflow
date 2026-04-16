"""Search request and response DTOs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.document import DocumentStatus, DocumentType


class SearchRequest(BaseModel):
    """Hybrid search: vector similarity + metadata filters."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural language search query",
        examples=["Python engineer with Kubernetes experience"],
    )
    document_type: DocumentType | None = Field(
        None, description="Filter by document category"
    )
    skills: list[str] | None = Field(
        None,
        description="Filter to documents mentioning these skills",
        examples=[["python", "kubernetes"]],
    )
    min_experience_years: int | None = Field(
        None, ge=0, description="Minimum years of experience"
    )
    date_from: datetime | None = Field(
        None, description="Documents uploaded after this timestamp"
    )
    date_to: datetime | None = Field(
        None, description="Documents uploaded before this timestamp"
    )
    limit: int = Field(10, ge=1, le=100, description="Maximum results to return")


class SearchHighlight(BaseModel):
    """A matching text chunk from the document."""

    text: str = Field(..., description="Chunk text that matched the query")
    chunk_index: int = Field(..., description="Position of this chunk in the document")


class SearchResultItem(BaseModel):
    """A single search result with relevance score and highlights."""

    document_id: UUID = Field(..., description="Matched document ID")
    filename: str = Field(..., description="Original filename")
    document_type: DocumentType | None = Field(
        None, description="Classified document category"
    )
    status: DocumentStatus = Field(..., description="Processing status")
    score: float = Field(
        ..., ge=0, le=1, description="Relevance score (0–1, higher is better)"
    )
    highlights: list[SearchHighlight] = Field(
        ..., description="Matching text chunks ranked by relevance"
    )
    metadata: dict | None = Field(
        None, description="Extracted metadata (skills, experience, etc.)"
    )


class SearchResponse(BaseModel):
    """Search results with timing info."""

    results: list[SearchResultItem] = Field(..., description="Ranked search results")
    total: int = Field(..., description="Total matching documents")
    query_time_ms: int = Field(..., description="Query execution time in milliseconds")
