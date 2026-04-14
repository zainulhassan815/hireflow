from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus, DocumentType


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    storage_key: str
    status: DocumentStatus
    document_type: DocumentType | None
    metadata_: dict | None
    created_at: datetime
    updated_at: datetime
