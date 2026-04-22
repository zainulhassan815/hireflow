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


class GmailConnection(BaseModel):
    """One Gmail mailbox connected to the current user.

    A user may hold multiple connections. The ``GET /gmail/connections``
    endpoint returns a (possibly empty) list of these; empty means "no
    mailbox connected yet".
    """

    id: UUID = Field(..., description="Stable identifier for this connection.")
    gmail_email: EmailStr = Field(..., description="The connected Gmail address.")
    connected_at: datetime = Field(
        ...,
        description="When the connection was first established.",
    )
    last_synced_at: datetime | None = Field(
        None,
        description=(
            "When the worker last polled this connection; null until the "
            "first sync run completes."
        ),
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="OAuth scopes the user granted for this connection.",
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
            "Watch ``last_synced_at`` on the list endpoint to know when "
            "it finishes."
        ),
    )
