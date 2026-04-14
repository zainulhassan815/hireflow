from datetime import datetime
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
