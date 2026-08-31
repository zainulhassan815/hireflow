"""Conversation and chat-message DTOs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.rag import SourceCitation


class Conversation(BaseModel):
    """One chat thread belonging to the current user."""

    id: UUID = Field(..., description="Stable identifier for this conversation.")
    title: str | None = Field(
        None,
        description=(
            "Short auto-generated name, written after the first exchange "
            "completes and editable afterwards. Null means the thread has "
            "not had a successful exchange yet."
        ),
        examples=["Sarah Chen Python experience"],
    )
    archived: bool = Field(
        False,
        description=(
            "Archived threads are hidden from the default listing but are "
            "not deleted. ``DELETE`` sets this rather than removing rows."
        ),
    )
    created_at: datetime = Field(..., description="When the thread was started.")
    updated_at: datetime = Field(
        ...,
        description=(
            "When the last turn landed. The list endpoint orders by this, newest first."
        ),
    )


class ConversationUpdate(BaseModel):
    """Editable fields on an existing conversation."""

    title: str | None = Field(
        None,
        max_length=200,
        description="Rename the thread. Omit to leave the current title.",
        examples=["Backend candidates shortlist"],
    )
    archived: bool | None = Field(
        None,
        description=(
            "Archive or restore. Omit to leave unchanged. Archiving hides "
            "the thread from the default listing; nothing is deleted."
        ),
    )


class ChatMessage(BaseModel):
    """One turn in a conversation.

    Assistant turns carry the same answer metadata the streaming
    endpoint emits, so a reloaded thread renders identically to one that
    was streamed live — same source chips, same confidence label.
    """

    id: UUID = Field(..., description="Stable identifier for this message.")
    role: str = Field(
        ...,
        description="``user`` or ``assistant``.",
        examples=["assistant"],
    )
    content: str = Field(..., description="The message text.")
    citations: list[SourceCitation] | None = Field(
        None,
        description=(
            "Source chunks behind an assistant answer. Null on user turns "
            "and on answers where retrieval returned nothing."
        ),
    )
    model: str | None = Field(
        None, description="LLM that produced an assistant answer.", examples=["claude"]
    )
    confidence: str | None = Field(
        None,
        description="Retrieval confidence: ``high``, ``medium`` or ``low``.",
        examples=["high"],
    )
    intent: str | None = Field(
        None,
        description="Classified answer shape for an assistant turn.",
        examples=["comparison"],
    )
    intent_confidence: float | None = Field(
        None, description="Classifier confidence for ``intent``.", examples=[0.82]
    )
    created_at: datetime = Field(..., description="When the turn was recorded.")


class ChatTurnRequest(BaseModel):
    """Ask a question inside a conversation.

    Same retrieval knobs as ``POST /rag/stream``; the difference is that
    prior turns in this conversation are loaded server-side and used both
    to resolve follow-up references before retrieval and as context for
    the answer.
    """

    question: str = Field(
        ...,
        min_length=1,
        description="The question to ask, in the user's own words.",
        examples=["What about her Python experience?"],
    )
    document_ids: list[UUID] | None = Field(
        None,
        description="Limit retrieval to specific documents. Null = search all.",
    )
    max_chunks: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum document chunks to feed the model as context.",
        examples=[5],
    )
