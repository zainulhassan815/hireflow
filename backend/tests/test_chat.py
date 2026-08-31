"""Conversation persistence + memory, against a real DB and a stub LLM.

Covers the properties that would hurt most if they broke:

* owner scoping — another user's thread is indistinguishable from a
  missing one on every route
* soft delete — DELETE archives, nothing is lost
* a failed turn keeps the question and discards the partial answer
* **condensation** — a follow-up retrieves against a standalone rewrite,
  not the raw pronoun question. This is the property that makes chat
  answer the right question; without it history is decorative.
* auto-title fires once, and a title failure never sinks the answer
"""

from __future__ import annotations

from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio


async def _make_conversation(client, token, auth_headers) -> str:
    r = await client.post("/api/conversations", headers=auth_headers(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _other_users_conversation() -> str:
    from app.core.db import SessionLocal
    from app.models import User, UserRole
    from app.repositories.conversation import ConversationRepository

    async with SessionLocal() as session:
        other = User(
            email=f"other-{uuid4()}@example.com",
            hashed_password="$argon2id$v=19$not-a-real-hash",
            role=UserRole.HR,
            is_active=True,
        )
        session.add(other)
        await session.commit()
        await session.refresh(other)
        conv = await ConversationRepository(session).create(owner_id=other.id)
        return str(conv.id)


# ---------------------------------------------------------------------------
# CRUD + owner scoping
# ---------------------------------------------------------------------------


async def test_create_and_list_conversations(client, admin_token, auth_headers) -> None:
    cid = await _make_conversation(client, admin_token, auth_headers)

    listed = await client.get("/api/conversations", headers=auth_headers(admin_token))
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [cid]
    assert listed.json()[0]["title"] is None
    assert listed.json()[0]["archived"] is False


async def test_rename_conversation(client, admin_token, auth_headers) -> None:
    cid = await _make_conversation(client, admin_token, auth_headers)
    r = await client.patch(
        f"/api/conversations/{cid}",
        json={"title": "Backend shortlist"},
        headers=auth_headers(admin_token),
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Backend shortlist"


async def test_delete_is_soft_and_restorable(client, admin_token, auth_headers) -> None:
    cid = await _make_conversation(client, admin_token, auth_headers)

    assert (
        await client.delete(
            f"/api/conversations/{cid}", headers=auth_headers(admin_token)
        )
    ).status_code == 204

    default = await client.get("/api/conversations", headers=auth_headers(admin_token))
    assert default.json() == []

    with_archived = await client.get(
        "/api/conversations?archived=true", headers=auth_headers(admin_token)
    )
    assert [c["id"] for c in with_archived.json()] == [cid]
    assert with_archived.json()[0]["archived"] is True

    restored = await client.patch(
        f"/api/conversations/{cid}",
        json={"archived": False},
        headers=auth_headers(admin_token),
    )
    assert restored.json()["archived"] is False


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", ""),
        ("patch", ""),
        ("delete", ""),
        ("get", "/messages"),
    ],
)
async def test_other_users_conversation_is_404(
    client, admin_token, auth_headers, method, suffix
) -> None:
    other_id = await _other_users_conversation()
    kwargs = {"headers": auth_headers(admin_token)}
    if method == "patch":
        kwargs["json"] = {"title": "mine now"}
    response = await getattr(client, method)(
        f"/api/conversations/{other_id}{suffix}", **kwargs
    )
    assert response.status_code == 404


async def test_missing_conversation_is_404(client, admin_token, auth_headers) -> None:
    bogus = "00000000-0000-0000-0000-000000000000"
    r = await client.get(
        f"/api/conversations/{bogus}", headers=auth_headers(admin_token)
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Streaming turn: persistence, memory, titling
# ---------------------------------------------------------------------------


class _StubRag:
    """Records what history it was handed and replays canned events."""

    def __init__(self, events):
        self._events = events
        self.seen_history = None
        self.seen_question = None

    async def stream_query(
        self, *, actor, question, document_ids, max_chunks, history=None
    ):
        self.seen_history = history
        self.seen_question = question
        for event in self._events:
            yield event


class _StubLlm:
    model_name = "stub"

    def __init__(self, reply="Sarah Chen Python Experience", fail=False):
        self._reply = reply
        self._fail = fail
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        if self._fail:
            raise RuntimeError("titling is down")
        return self._reply

    def stream(self, system, user):  # pragma: no cover - unused
        raise NotImplementedError


def _answer_events(text="Sarah knows Python well."):
    from app.schemas.rag import DeltaEvent, DoneEvent, StreamDone

    return [
        DeltaEvent(data=text),
        DoneEvent(
            data=StreamDone(
                model="stub",
                query_time_ms=12,
                confidence="high",
                intent="general",
                intent_confidence=0.9,
            )
        ),
    ]


async def _drain(rag, llm, owner, conversation_id, question):
    """Run one turn through a real ChatService.

    The read-side session is opened and closed around the turn — leaking
    it holds a transaction open and the next test's TRUNCATE blocks on
    it forever. In production FastAPI closes this session for us.
    """
    from app.core.db import SessionLocal
    from app.repositories.conversation import ConversationRepository
    from app.services.chat_service import ChatService

    async with SessionLocal() as session:
        service = ChatService(
            conversations=ConversationRepository(session),
            rag=rag,
            llm=llm,
            session_factory=SessionLocal,
            history_max_turns=10,
        )
        return [
            e
            async for e in service.stream_turn(
                owner=owner,
                conversation_id=conversation_id,
                question=question,
                document_ids=None,
                max_chunks=5,
            )
        ]


async def _messages(conversation_id):
    from app.core.db import SessionLocal
    from app.repositories.conversation import ConversationRepository

    async with SessionLocal() as session:
        return await ConversationRepository(session).list_messages(conversation_id)


async def _conversation(conversation_id):
    from app.core.db import SessionLocal
    from app.repositories.conversation import ConversationRepository

    async with SessionLocal() as session:
        return await ConversationRepository(session).get_by_id(conversation_id)


async def _new_conversation(owner):
    from app.core.db import SessionLocal
    from app.repositories.conversation import ConversationRepository

    async with SessionLocal() as session:
        conv = await ConversationRepository(session).create(owner_id=owner.id)
        return conv.id


async def test_turn_persists_both_sides_with_metadata(admin_user) -> None:
    cid = await _new_conversation(admin_user)
    await _drain(
        _StubRag(_answer_events()),
        _StubLlm(),
        admin_user,
        cid,
        "Tell me about Sarah Chen",
    )

    msgs = await _messages(cid)
    assert [m.role.value for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "Tell me about Sarah Chen"
    assert msgs[1].content == "Sarah knows Python well."
    # Answer metadata is stored, so a reloaded thread renders the same
    # confidence and intent the live stream showed.
    assert msgs[1].confidence == "high"
    assert msgs[1].intent == "general"
    assert msgs[1].model == "stub"


async def test_failed_turn_keeps_question_and_drops_partial_answer(
    admin_user,
) -> None:
    from app.schemas.errors import ErrorBody
    from app.schemas.rag import DeltaEvent, ErrorEvent

    cid = await _new_conversation(admin_user)
    events = [
        DeltaEvent(data="Sarah kno"),
        ErrorEvent(data=ErrorBody(code="llm_timeout", message="provider timed out")),
    ]
    await _drain(
        _StubRag(events), _StubLlm(), admin_user, cid, "Tell me about Sarah Chen"
    )

    msgs = await _messages(cid)
    assert [m.role.value for m in msgs] == ["user"]
    assert msgs[0].content == "Tell me about Sarah Chen"
    # No title either — there was no successful exchange to name.
    assert (await _conversation(cid)).title is None


async def test_prior_turns_are_passed_as_history(admin_user) -> None:
    cid = await _new_conversation(admin_user)
    first = _StubRag(_answer_events("Sarah Chen is a senior engineer."))
    await _drain(first, _StubLlm(), admin_user, cid, "Who is Sarah?")
    assert first.seen_history == []

    second = _StubRag(_answer_events("She has 8 years of Python."))
    await _drain(
        second, _StubLlm(), admin_user, cid, "What about her Python experience?"
    )

    assert [(t.role, t.content) for t in second.seen_history] == [
        ("user", "Who is Sarah?"),
        ("assistant", "Sarah Chen is a senior engineer."),
    ]
    # The model is still asked the user's own wording.
    assert second.seen_question == "What about her Python experience?"


async def test_auto_title_fires_once(admin_user) -> None:
    cid = await _new_conversation(admin_user)
    llm = _StubLlm(reply='"Sarah Chen Python Experience."')

    await _drain(_StubRag(_answer_events()), llm, admin_user, cid, "Q1")
    # Quotes and trailing period stripped.
    assert (await _conversation(cid)).title == "Sarah Chen Python Experience"
    assert llm.calls == 1

    await _drain(_StubRag(_answer_events()), llm, admin_user, cid, "Q2")
    assert llm.calls == 1, "titling must not re-run on an already-titled thread"


async def test_title_failure_does_not_sink_the_turn(admin_user) -> None:
    cid = await _new_conversation(admin_user)
    await _drain(
        _StubRag(_answer_events()),
        _StubLlm(fail=True),
        admin_user,
        cid,
        "Tell me about Sarah Chen",
    )

    msgs = await _messages(cid)
    assert [m.role.value for m in msgs] == ["user", "assistant"]
    assert (await _conversation(cid)).title is None


# ---------------------------------------------------------------------------
# Condensation — the property that makes follow-ups retrieve correctly
# ---------------------------------------------------------------------------


class _RecordingRetriever:
    def __init__(self):
        self.queries: list[str] = []

    async def retrieve_chunks(self, *, actor, query, document_ids, limit):
        self.queries.append(query)
        return []

    async def retrieve_candidate_summaries(self, *, actor, query, limit):
        return []


def _rag_with(retriever, llm):
    from unittest.mock import MagicMock

    from app.services.rag_service import RagService

    return RagService(retriever, llm, MagicMock())


async def test_followup_retrieves_against_the_rewritten_question(admin_user) -> None:
    """A pronoun follow-up must not be embedded as written.

    'What about her Python experience?' has no referent on its own — the
    vector search matches nothing useful and the model then answers
    confidently over unrelated chunks. Injecting history into the prompt
    cannot fix that, because retrieval runs first.
    """
    from app.services.rag_service import ChatTurn

    retriever = _RecordingRetriever()
    llm = _StubLlm(reply="What Python experience does Sarah Chen have?")
    rag = _rag_with(retriever, llm)

    await rag._build_context(
        actor=admin_user,
        question="What about her Python experience?",
        document_ids=None,
        max_chunks=5,
        history=[
            ChatTurn("user", "Tell me about Sarah Chen"),
            ChatTurn("assistant", "Sarah Chen is a senior engineer."),
        ],
    )

    assert retriever.queries == ["What Python experience does Sarah Chen have?"]


async def test_first_turn_skips_condensation(admin_user) -> None:
    """No history means nothing to resolve — and no extra LLM call."""
    retriever = _RecordingRetriever()
    llm = _StubLlm()
    rag = _rag_with(retriever, llm)

    await rag._build_context(
        actor=admin_user,
        question="Who has Python experience?",
        document_ids=None,
        max_chunks=5,
        history=None,
    )

    assert retriever.queries == ["Who has Python experience?"]
    assert llm.calls == 0


async def test_condense_failure_falls_back_to_the_raw_question(admin_user) -> None:
    """A condense outage degrades recall, it does not fail the turn."""
    from app.services.rag_service import ChatTurn

    retriever = _RecordingRetriever()
    rag = _rag_with(retriever, _StubLlm(fail=True))

    await rag._build_context(
        actor=admin_user,
        question="What about her Python experience?",
        document_ids=None,
        max_chunks=5,
        history=[ChatTurn("user", "Tell me about Sarah Chen")],
    )

    assert retriever.queries == ["What about her Python experience?"]
