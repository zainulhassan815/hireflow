"""Gmail OAuth DTOs."""

from datetime import UTC, date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


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
    backfill_before: datetime | None = Field(
        None,
        description=(
            "How far back the historical backfill has walked so far. Null "
            "means no backfill is running — either none was requested or "
            "the last one finished. While set, each sync run pulls another "
            "batch of older mail and moves this further into the past."
        ),
        examples=["2025-11-04T00:00:00Z"],
    )
    backfill_until: datetime | None = Field(
        None,
        description=(
            "The date the running backfill stops at. Null when no backfill "
            "is in progress."
        ),
        examples=["2024-01-01T00:00:00Z"],
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


class GmailBackfillRequest(BaseModel):
    """Start a historical backfill for one connection."""

    until: date = Field(
        ...,
        description=(
            "Oldest date to pull mail from. The backfill walks backwards "
            "from the start of the incremental window towards this date, a "
            "batch per sync run, and stops on reaching it. Must be in the "
            "past."
        ),
        examples=["2024-01-01"],
    )

    @field_validator("until")
    @classmethod
    def _must_be_past(cls, value: date) -> date:
        if value >= datetime.now(UTC).date():
            raise ValueError("until must be a date in the past")
        return value


class GmailBackfillResponse(BaseModel):
    """Returned by the backfill trigger endpoint (202 Accepted)."""

    connection_id: UUID = Field(
        ..., description="The connection now walking backwards through history."
    )
    backfill_before: datetime = Field(
        ...,
        description=(
            "Where the walk starts — the far edge of the window incremental "
            "sync already covers, so the backfill doesn't re-tread it."
        ),
        examples=["2026-08-24T00:00:00Z"],
    )
    backfill_until: datetime = Field(
        ...,
        description="The date the walk stops at.",
        examples=["2024-01-01T00:00:00Z"],
    )
    queued: bool = Field(
        default=True,
        description=(
            "Always true — the first batch was handed to the worker queue. "
            "Watch ``backfill_before`` on the list endpoint to follow "
            "progress; it returns to null when the walk completes."
        ),
    )
