"""Gmail OAuth DTOs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class GmailAuthorizeResponse(BaseModel):
    """Redirect target for the Gmail OAuth consent flow."""

    authorize_url: str = Field(
        ...,
        description=(
            "Google's OAuth consent URL. The frontend redirects the browser "
            "here; Google will call the backend's callback endpoint when the "
            "user approves or denies."
        ),
        examples=["https://accounts.google.com/o/oauth2/v2/auth?..."],
    )


class GmailConnectionStatus(BaseModel):
    """Current user's Gmail connection (empty fields if not connected)."""

    connected: bool = Field(
        ..., description="True if a Gmail connection exists for the current user."
    )
    gmail_email: EmailStr | None = Field(
        None, description="The connected Gmail address, if any."
    )
    connected_at: datetime | None = Field(
        None, description="When the current connection was established."
    )
    last_synced_at: datetime | None = Field(
        None, description="When F51 last polled this connection; null until F51 runs."
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="OAuth scopes the user granted.",
    )


class GmailSyncTriggerResponse(BaseModel):
    """Returned by the manual sync trigger endpoint (202 Accepted)."""

    connection_id: UUID = Field(
        ..., description="The connection that was enqueued for sync."
    )
    queued: bool = Field(
        default=True,
        description=(
            "Always true — the task was handed to the worker queue. "
            "Watch ``last_synced_at`` on the status endpoint to know "
            "when it finishes."
        ),
    )
