"""Tiny helpers for building realistic domain objects in tests.

These are *not* Faker-style factories with random data — they return
deterministic rows so test failures are reproducible. Override the
kwargs to vary specific fields.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from app.models import GmailConnection, GmailIngestedMessage, GmailIngestStatus


async def make_gmail_connection(
    session,
    *,
    user_id: UUID,
    gmail_email: str = "candidate-source@example.com",
    refresh_token: str = "stored-refresh-token",
    scopes: list[str] | None = None,
) -> GmailConnection:
    connection = GmailConnection(
        user_id=user_id,
        gmail_email=gmail_email,
        refresh_token=refresh_token,
        scopes=scopes
        or [
            "openid",
            "email",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
        ],
    )
    session.add(connection)
    await session.commit()
    await session.refresh(connection)
    return connection


async def make_ingested_message(
    session,
    *,
    connection_id: UUID,
    gmail_message_id: str | None = None,
    status: GmailIngestStatus = GmailIngestStatus.COMPLETED,
) -> GmailIngestedMessage:
    row = GmailIngestedMessage(
        connection_id=connection_id,
        gmail_message_id=gmail_message_id or uuid4().hex,
        ingest_status=status,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row
