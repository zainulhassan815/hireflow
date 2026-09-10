from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.encryption import EncryptedString
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class GmailConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per (user, connected Gmail address).

    A user may connect multiple mailboxes (e.g. a recruiting inbox and
    a personal inbox). Re-authorizing an already-connected address
    updates the stored tokens in place; connecting a new address adds
    a row. Uniqueness is enforced by the composite constraint below.
    """

    __tablename__ = "gmail_connections"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "gmail_email", name="uq_gmail_connections_user_email"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    gmail_email: Mapped[str] = mapped_column(String(320), nullable=False)
    refresh_token: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Historical backfill walks backwards in time, one batch per sync run.
    # ``backfill_before`` is the exclusive upper bound of the next batch and
    # doubles as the "is backfilling" flag; ``backfill_until`` is the floor
    # the walk stops at. Both null means no backfill in progress.
    backfill_before: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    backfill_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Set when Google rejects the stored refresh token. The row, its
    # ingest ledger, backfill cursor and mirroring setting all survive,
    # so reconnecting the same address lands on this same row via
    # UNIQUE (user_id, gmail_email) and re-imports nothing. Deleting the
    # row instead would cascade the ledger away and duplicate every
    # document on the next sync.
    #
    # The stored refresh_token is left in place: it is known dead but
    # inert, and the column is NOT NULL.
    reauth_required_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Cursor into Gmail's history feed. Null means "not seeded yet" —
    # either a fresh connection or a cursor Google aged out (history
    # survives roughly a week, sometimes only hours), in which case the
    # next run re-seeds and the changes inside the gap are lost.
    last_history_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Opt-in: when true, a message Gmail reports as *permanently* deleted
    # takes its ingested documents down with it. Off by default and never
    # enabled implicitly — deletion drops blobs and embeddings, cascades
    # through candidate_attachments, and cannot be undone.
    mirror_deletions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
