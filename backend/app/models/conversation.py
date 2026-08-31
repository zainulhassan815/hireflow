from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One chat thread, private to its owner.

    Deletion is soft: ``archived`` hides a thread from the default
    listing but keeps it recoverable, since a thread is often the only
    record of how a hiring question was reasoned through.
    """

    __tablename__ = "conversations"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Null until the first exchange completes and the auto-titler runs.
    # A null title is also the trigger: titling fires when an assistant
    # message lands on a conversation that still has none, so a first
    # turn that errored doesn't leave the thread permanently untitled.
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=None
    )

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One turn in a conversation.

    Assistant turns carry the answer metadata the UI already renders for
    live messages — citations, model, intent, confidence — so a reloaded
    thread looks identical to the one that was streamed rather than
    silently losing its source chips and confidence label.
    """

    __tablename__ = "chat_messages"
    __table_args__ = (
        # Every read is "this conversation's messages, oldest first".
        Index("ix_chat_messages_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[ChatRole] = mapped_column(
        SAEnum(
            ChatRole,
            name="chat_role",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    intent_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
