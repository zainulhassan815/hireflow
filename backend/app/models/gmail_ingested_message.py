from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class GmailIngestStatus(StrEnum):
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    RESET = "reset"


class GmailIngestedMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per Gmail message we've seen for a connection.

    Acts as the dedup ledger plus an audit trail for what was ingested.
    The ``(connection_id, gmail_message_id)`` unique constraint is the
    safety net: every ingest run tries to ``INSERT`` and trusts the DB
    to enforce "at most once per message."
    """

    __tablename__ = "gmail_ingested_messages"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "gmail_message_id",
            name="uq_gmail_ingested_connection_message",
        ),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gmail_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gmail_message_id: Mapped[str] = mapped_column(String(255), nullable=False)

    ingest_status: Mapped[GmailIngestStatus] = mapped_column(
        SAEnum(
            GmailIngestStatus,
            name="gmail_ingest_status",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=GmailIngestStatus.CLAIMED,
        nullable=False,
        index=True,
    )

    attachment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    document_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
