from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus, DocumentType


class DocumentResponse(BaseModel):
    """Metadata for an uploaded document."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique document identifier")
    owner_id: UUID = Field(..., description="ID of the user who uploaded this document")
    filename: str = Field(
        ...,
        description="Original filename at upload time",
        examples=["resume.pdf"],
    )
    mime_type: str = Field(
        ..., description="MIME type of the file", examples=["application/pdf"]
    )
    size_bytes: int = Field(..., description="File size in bytes", examples=[204800])
    storage_key: str = Field(
        ...,
        description="Object-storage key (internal; use the download endpoint to fetch content)",
    )
    status: DocumentStatus = Field(
        ...,
        description=(
            "Processing pipeline status: pending → processing → ready | failed"
        ),
    )
    document_type: DocumentType | None = Field(
        None,
        description="Detected document category (resume, report, contract, letter, other)",
    )
    metadata: dict | None = Field(
        None,
        description="Extracted metadata (skills, experience, education, etc.)",
        alias="metadata_",
    )
    created_at: datetime = Field(..., description="Upload timestamp (UTC)")
    updated_at: datetime = Field(..., description="Last modification timestamp (UTC)")


class DocumentMetadataResponse(BaseModel):
    """Extracted metadata and classification for a processed document."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Document identifier")
    filename: str = Field(..., description="Original filename")
    document_type: DocumentType | None = Field(
        None, description="Classified document category"
    )
    status: DocumentStatus = Field(..., description="Processing status")
    metadata: dict | None = Field(
        None,
        description=(
            "Structured metadata extracted from the document. "
            "For resumes: skills, experience_years, education, emails, phones, "
            "classification_confidence. For other types: varies."
        ),
        alias="metadata_",
    )
    extracted_text: str | None = Field(None, description="Full extracted text content")


class SimilarDocumentsRequest(BaseModel):
    """Query body for the similarity-search endpoint (F89.c)."""

    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of neighbours to return (1–50).",
        examples=[10],
    )


class SimilarDocument(BaseModel):
    """One neighbour from the similarity-search response (F89.c)."""

    document_id: UUID = Field(..., description="Neighbour document identifier")
    filename: str = Field(
        ...,
        description="Neighbour document original filename",
        examples=["senior_engineer_resume.pdf"],
    )
    document_type: DocumentType | None = Field(
        None, description="Neighbour document classified category"
    )
    similarity: float = Field(
        ...,
        description=(
            "Cosine similarity to the source document in [0.0, 1.0]; "
            "higher values indicate a closer topical match."
        ),
        examples=[0.87],
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Neighbour document's extracted metadata (skills, "
            "experience_years, etc.) for UI context without a follow-up "
            "fetch."
        ),
    )


class SimilarDocumentsResponse(BaseModel):
    """Response envelope for the similarity-search endpoint (F89.c)."""

    source_document_id: UUID = Field(
        ..., description="Source document the neighbours were ranked against"
    )
    results: list[SimilarDocument] = Field(
        default_factory=list,
        description="Neighbours ordered by similarity descending.",
    )
