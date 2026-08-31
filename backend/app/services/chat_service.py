"""Conversation orchestration: persistence around the RAG stream.

Owns the chat-shaped concerns ``RagService`` deliberately does not:
loading history, writing turns, and titling. ``RagService`` stays
persistence-free so the stateless ``/rag/*`` routes keep working
unchanged.

Session discipline matters here. The streaming path does **not** hold
the request-scoped session across generation — an LLM turn runs for
seconds and would pin a pooled connection the whole time. Each write
opens its own short-lived session instead:

    open → persist user turn → close
    stream (no connection held)
    open → persist assistant turn + touch → close
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.adapters.protocols import LlmProvider
from app.domain.exceptions import NotFound
from app.models import ChatMessage, ChatRole, Conversation, User
from app.repositories.conversation import ConversationRepository
from app.schemas.rag import CitationsEvent, DeltaEvent, DoneEvent, ErrorEvent
from app.services.rag_service import ChatTurn, RagService

logger = logging.getLogger(__name__)

_TITLE_SYSTEM = """\
You write a short title for a chat thread.

Rules:
- 3 to 6 words.
- No quotes, no trailing period, no "Chat about".
- Name the subject: a candidate, a role, a document, a topic.
- Output only the title."""

_TITLE_ANSWER_CHARS = 200
_TITLE_MAX_CHARS = 200


class ChatService:
    def __init__(
        self,
        *,
        conversations: ConversationRepository,
        rag: RagService,
        llm: LlmProvider,
        session_factory: async_sessionmaker,
        history_max_turns: int,
    ) -> None:
        self._conversations = conversations
        self._rag = rag
        # Its own handle rather than RagService's — titling is this
        # service's concern, not something to borrow through a private.
        self._llm = llm
        self._session_factory = session_factory
        self._history_max_turns = history_max_turns

    # ---------- conversation CRUD ----------

    async def create(self, owner: User) -> Conversation:
        return await self._conversations.create(owner_id=owner.id)

    async def list(self, owner: User, *, include_archived: bool) -> list[Conversation]:
        return await self._conversations.list_for_user(
            owner.id, include_archived=include_archived
        )

    async def get(self, owner: User, conversation_id: UUID) -> Conversation:
        conv = await self._conversations.get_for_user(owner.id, conversation_id)
        if conv is None:
            raise NotFound("Conversation not found.")
        return conv

    async def update(
        self,
        owner: User,
        conversation_id: UUID,
        *,
        title: str | None = None,
        archived: bool | None = None,
    ) -> Conversation:
        conv = await self.get(owner, conversation_id)
        return await self._conversations.update(conv, title=title, archived=archived)

    async def archive(self, owner: User, conversation_id: UUID) -> None:
        """Soft delete. The thread is often the only record of how a
        hiring question was reasoned through, so it stays recoverable."""
        conv = await self.get(owner, conversation_id)
        await self._conversations.update(conv, archived=True)

    async def messages(self, owner: User, conversation_id: UUID) -> list[ChatMessage]:
        await self.get(owner, conversation_id)
        return await self._conversations.list_messages(conversation_id)

    # ---------- streaming turn ----------

    async def stream_turn(
        self,
        *,
        owner: User,
        conversation_id: UUID,
        question: str,
        document_ids: list[UUID] | None,
        max_chunks: int,
    ) -> AsyncIterator[CitationsEvent | DeltaEvent | DoneEvent | ErrorEvent]:
        conv = await self.get(owner, conversation_id)

        history = [
            ChatTurn(role=m.role.value, content=m.content)
            for m in await self._conversations.recent_messages(
                conv.id, limit=self._history_max_turns
            )
        ]

        # Persisted before a single token is generated: whatever the user
        # typed survives a mid-stream disconnect or provider failure.
        async with self._session_factory() as session:
            await ConversationRepository(session).add_message(
                conversation_id=conv.id, role=ChatRole.USER, content=question
            )

        answer_parts: list[str] = []
        citations: list[dict] = []
        done: DoneEvent | None = None

        async for event in self._rag.stream_query(
            actor=owner,
            question=question,
            document_ids=document_ids,
            max_chunks=max_chunks,
            history=history,
        ):
            if isinstance(event, DeltaEvent):
                answer_parts.append(event.data)
            elif isinstance(event, CitationsEvent):
                citations = [c.model_dump(mode="json") for c in event.data]
            elif isinstance(event, DoneEvent):
                done = event
            yield event

        if done is None:
            # Errored or the client vanished. The user's question stays
            # saved; the half-generated answer does not, so a reload shows
            # a question awaiting a retry rather than a truncated reply.
            logger.info("turn on %s ended without done; not persisting", conv.id)
            return

        await self._persist_answer(
            conversation_id=conv.id,
            question=question,
            answer="".join(answer_parts),
            citations=citations,
            done=done,
        )

    async def _persist_answer(
        self,
        *,
        conversation_id: UUID,
        question: str,
        answer: str,
        citations: list[dict],
        done: DoneEvent,
    ) -> None:
        async with self._session_factory() as session:
            repo = ConversationRepository(session)
            await repo.add_message(
                conversation_id=conversation_id,
                role=ChatRole.ASSISTANT,
                content=answer,
                citations=citations or None,
                model=done.data.model,
                confidence=done.data.confidence,
                intent=done.data.intent,
                intent_confidence=done.data.intent_confidence,
            )
            conv = await repo.get_by_id(conversation_id)
            if conv is None:
                return
            await repo.touch(conv)
            if conv.title is None:
                title = await self._generate_title(question, answer)
                if title:
                    await repo.update(conv, title=title)

    async def _generate_title(self, question: str, answer: str) -> str | None:
        """Name the thread from its first exchange.

        Triggered by ``title IS NULL`` rather than by a turn counter, so a
        first turn that errored doesn't leave the thread unnamed forever.
        Failure is swallowed: a titling error must never sink a turn that
        already produced an answer.
        """
        prompt = (
            f"Question: {question}\n\nAnswer: {answer[:_TITLE_ANSWER_CHARS]}\n\nTitle:"
        )
        try:
            title = await asyncio.to_thread(self._llm.complete, _TITLE_SYSTEM, prompt)
        except Exception:
            logger.warning("auto-title failed; leaving conversation untitled")
            return None
        return title.strip().strip('"').rstrip(".")[:_TITLE_MAX_CHARS] or None
