"""Data access for conversations and their messages.

Everything here is owner-scoped by construction: ``get_for_user``
returns ``None`` both for a missing id and for one belonging to another
user, so routes translate either to 404 and never leak existence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, ChatRole, Conversation


class ConversationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, *, owner_id: UUID) -> Conversation:
        conv = Conversation(owner_id=owner_id)
        self._db.add(conv)
        await self._db.commit()
        await self._db.refresh(conv)
        return conv

    async def get_for_user(
        self, user_id: UUID, conversation_id: UUID
    ) -> Conversation | None:
        result = await self._db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.owner_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        """Unscoped lookup — only for the post-stream writer, which has
        already authorised the caller. HTTP handlers use ``get_for_user``."""
        return await self._db.get(Conversation, conversation_id)

    async def list_for_user(
        self, user_id: UUID, *, include_archived: bool = False
    ) -> list[Conversation]:
        stmt = select(Conversation).where(Conversation.owner_id == user_id)
        if not include_archived:
            stmt = stmt.where(Conversation.archived.is_(False))
        result = await self._db.execute(stmt.order_by(Conversation.updated_at.desc()))
        return list(result.scalars().all())

    async def update(
        self,
        conv: Conversation,
        *,
        title: str | None = None,
        archived: bool | None = None,
    ) -> Conversation:
        if title is not None:
            conv.title = title
        if archived is not None:
            conv.archived = archived
        await self._db.commit()
        await self._db.refresh(conv)
        return conv

    async def touch(self, conv: Conversation) -> None:
        """Bump ``updated_at`` so the thread sorts to the top of the list.

        Written explicitly rather than relying on ``onupdate``: that only
        fires when some column actually changes, and a turn adds rows to
        ``chat_messages`` without touching the conversation itself.
        """
        conv.updated_at = datetime.now(UTC)
        await self._db.commit()

    async def add_message(
        self,
        *,
        conversation_id: UUID,
        role: ChatRole,
        content: str,
        citations: list | None = None,
        model: str | None = None,
        confidence: str | None = None,
        intent: str | None = None,
        intent_confidence: float | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            citations=citations,
            model=model,
            confidence=confidence,
            intent=intent,
            intent_confidence=intent_confidence,
        )
        self._db.add(message)
        await self._db.commit()
        await self._db.refresh(message)
        return message

    async def list_messages(self, conversation_id: UUID) -> list[ChatMessage]:
        result = await self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.asc())
        )
        return list(result.scalars().all())

    async def recent_messages(
        self, conversation_id: UUID, *, limit: int
    ) -> list[ChatMessage]:
        """Newest ``limit`` messages, returned oldest-first.

        Fetches descending so the cap keeps the *most recent* turns, then
        reverses — the prompt needs chronological order.
        """
        result = await self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))
