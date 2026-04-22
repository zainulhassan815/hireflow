from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
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
