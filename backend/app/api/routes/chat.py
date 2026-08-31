"""Conversation CRUD plus the streaming chat turn.

``POST /conversations/{id}/messages`` is the chat-shaped counterpart to
``POST /rag/stream``: identical SSE event vocabulary, but the server
loads prior turns from the conversation, uses them to resolve follow-up
references before retrieval, and persists both sides of the exchange.

``/rag/query`` and ``/rag/stream`` stay as they are — stateless,
single-shot, and still used by the eval harness.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.deps import ChatServiceDep, CurrentUser
from app.api.routes.rag import _sse_frame
from app.schemas.chat import (
    ChatMessage,
    ChatTurnRequest,
    Conversation,
    ConversationUpdate,
)
from app.schemas.errors import ErrorResponse
from app.schemas.rag import SourceCitation

router = APIRouter()

_NOT_FOUND = {
    "model": ErrorResponse,
    "description": "Conversation not found or not owned by the current user",
}
_UNAUTHENTICATED = {"model": ErrorResponse, "description": "Not authenticated"}


def _to_schema(conv) -> Conversation:
    return Conversation(
        id=conv.id,
        title=conv.title,
        archived=conv.archived,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


def _message_to_schema(msg) -> ChatMessage:
    return ChatMessage(
        id=msg.id,
        role=msg.role.value,
        content=msg.content,
        citations=[SourceCitation(**c) for c in msg.citations]
        if msg.citations
        else None,
        model=msg.model,
        confidence=msg.confidence,
        intent=msg.intent,
        intent_confidence=msg.intent_confidence,
        created_at=msg.created_at,
    )


@router.post(
    "",
    response_model=Conversation,
    status_code=201,
    summary="Start a conversation",
    description=(
        "Creates an empty thread and returns it. The frontend calls this "
        "on the first message rather than on page open, so abandoned "
        "'new chat' clicks don't litter the list."
    ),
    responses={401: _UNAUTHENTICATED},
)
async def create_conversation(
    current_user: CurrentUser, chat: ChatServiceDep
) -> Conversation:
    return _to_schema(await chat.create(current_user))


@router.get(
    "",
    response_model=list[Conversation],
    summary="List conversations",
    description=(
        "Threads owned by the current user, most recently active first. "
        "Archived threads are excluded unless ``archived=true``."
    ),
    responses={401: _UNAUTHENTICATED},
)
async def list_conversations(
    current_user: CurrentUser,
    chat: ChatServiceDep,
    archived: bool = Query(
        False, description="Include archived threads in the result."
    ),
) -> list[Conversation]:
    return [
        _to_schema(c) for c in await chat.list(current_user, include_archived=archived)
    ]


@router.get(
    "/{conversation_id}",
    response_model=Conversation,
    summary="Get a conversation",
    responses={401: _UNAUTHENTICATED, 404: _NOT_FOUND},
)
async def get_conversation(
    conversation_id: UUID, current_user: CurrentUser, chat: ChatServiceDep
) -> Conversation:
    return _to_schema(await chat.get(current_user, conversation_id))


@router.patch(
    "/{conversation_id}",
    response_model=Conversation,
    summary="Rename or archive a conversation",
    description=(
        "Updates the fields present in the body and leaves the rest "
        "untouched. Use this to rename a thread or to restore an archived "
        "one (``archived: false``)."
    ),
    responses={401: _UNAUTHENTICATED, 404: _NOT_FOUND},
)
async def update_conversation(
    conversation_id: UUID,
    body: ConversationUpdate,
    current_user: CurrentUser,
    chat: ChatServiceDep,
) -> Conversation:
    conv = await chat.update(
        current_user, conversation_id, title=body.title, archived=body.archived
    )
    return _to_schema(conv)


@router.delete(
    "/{conversation_id}",
    status_code=204,
    summary="Archive a conversation",
    description=(
        "**Soft delete.** Sets ``archived`` and drops the thread from the "
        "default listing; no rows are removed and no messages are lost. "
        'Restore it with ``PATCH {"archived": false}``, or list it again '
        "with ``GET /conversations?archived=true``."
    ),
    responses={401: _UNAUTHENTICATED, 404: _NOT_FOUND},
)
async def delete_conversation(
    conversation_id: UUID, current_user: CurrentUser, chat: ChatServiceDep
) -> None:
    await chat.archive(current_user, conversation_id)


@router.get(
    "/{conversation_id}/messages",
    response_model=list[ChatMessage],
    summary="List messages in a conversation",
    description=(
        "Every turn, oldest first. A trailing ``user`` message with no "
        "``assistant`` reply means that turn failed mid-stream — the "
        "question was kept, the partial answer was not."
    ),
    responses={401: _UNAUTHENTICATED, 404: _NOT_FOUND},
)
async def list_messages(
    conversation_id: UUID, current_user: CurrentUser, chat: ChatServiceDep
) -> list[ChatMessage]:
    return [
        _message_to_schema(m)
        for m in await chat.messages(current_user, conversation_id)
    ]


@router.post(
    "/{conversation_id}/messages",
    summary="Ask a question in a conversation (streaming)",
    description=(
        "Server-Sent Events, with the same event vocabulary as "
        "``POST /rag/stream`` — ``citations``, ``delta``, ``done``, "
        "``error`` — so one client parser handles both.\n\n"
        "What differs is memory. Prior turns are loaded server-side and "
        "used twice: to rewrite a follow-up into a standalone question "
        "before retrieval (so *'what about her Python experience?'* "
        "retrieves against the person named earlier), and as context for "
        "the answer itself. The question you send is what the model is "
        "asked; only retrieval sees the rewrite.\n\n"
        "The user turn is persisted before generation starts, so a "
        "dropped connection never loses what was typed. The assistant "
        "turn is persisted only when the stream closes cleanly — a failed "
        "turn leaves the question awaiting a retry rather than a "
        "truncated answer."
    ),
    responses={
        200: {
            "description": "SSE stream of RAG events (see ``POST /rag/stream``).",
            "content": {"text/event-stream": {}},
        },
        401: _UNAUTHENTICATED,
        404: _NOT_FOUND,
    },
)
async def stream_message(
    conversation_id: UUID,
    body: ChatTurnRequest,
    current_user: CurrentUser,
    chat: ChatServiceDep,
) -> StreamingResponse:
    # Resolve ownership before opening the stream so an unauthorised or
    # missing id gets a plain 404 envelope rather than an SSE error frame.
    await chat.get(current_user, conversation_id)

    async def events() -> AsyncIterator[str]:
        async for event in chat.stream_turn(
            owner=current_user,
            conversation_id=conversation_id,
            question=body.question,
            document_ids=body.document_ids,
            max_chunks=body.max_chunks,
        ):
            yield _sse_frame(event)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
