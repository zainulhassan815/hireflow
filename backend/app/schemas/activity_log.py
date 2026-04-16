"""Activity log DTOs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.activity_log import ActivityAction


class ActivityLogResponse(BaseModel):
    """A single activity log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Log entry ID")
    actor_id: UUID | None = Field(None, description="User who performed the action")
    action: ActivityAction = Field(..., description="Action type")
    resource_type: str | None = Field(
        None, description="Type of resource affected (document, job, etc.)"
    )
    resource_id: str | None = Field(None, description="ID of the affected resource")
    detail: str | None = Field(None, description="Human-readable description")
    ip_address: str | None = Field(None, description="Client IP address")
    created_at: datetime = Field(..., description="When the action occurred (UTC)")
