"""End-to-end Gmail sync against mocked Google HTTP + real DB/Redis.

Covers the F51 invariants that would hurt most if they broke:

* ``claim_or_skip`` state machine — new / completed / failed / reset
* ``reset_stale_claims`` visibility timeout
* Full sync happy path (token refresh → list → get → download → upload → mark)
* Dedup on re-run (second run sees ``dedup=1``)
* Auto-disconnect on ``invalid_grant``
* Auto-candidate hook (via ``SyncCandidateService.handle_document_ready``)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from tests.factories import make_gmail_connection, make_ingested_message
from tests.gmail_responses import (
    ATTACHMENT_IMAGE,
    ATTACHMENT_PDF_1,
    ATTACHMENT_PDF_2,
    GET_MESSAGE_RESPONSE,
    LIST_MESSAGES_EMPTY,
    LIST_MESSAGES_RESPONSE,
    MESSAGE_ID,
    TOKEN_RESPONSE,
    attachment_response,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def gmail_oauth_configured(monkeypatch):
    """Same OAuth wiring as the OAuth test module."""
    from pydantic import SecretStr

    from app.adapters.gmail_oauth import GoogleGmailOAuth
    from app.api import deps

    monkeypatch.setattr(deps.settings, "gmail_client_id", "test-id")
    monkeypatch.setattr(deps.settings, "gmail_client_secret", SecretStr("test-secret"))
    monkeypatch.setattr(
        deps.settings,
        "gmail_redirect_uri",
        "http://localhost:8080/api/auth/gmail/callback",
    )
    monkeypatch.setattr(
        deps,
        "_gmail_oauth",
        GoogleGmailOAuth(
            client_id="test-id",
            client_secret="test-secret",
            redirect_uri="http://localhost:8080/api/auth/gmail/callback",
        ),
    )


@pytest.fixture
async def connection(admin_user):
    from app.core.db import SessionLocal

    async with SessionLocal() as session:
        return await make_gmail_connection(session, user_id=admin_user.id)


# ---------------------------------------------------------------------------
# claim_or_skip state machine
# ---------------------------------------------------------------------------


async def test_claim_or_skip_claims_new_message(connection) -> None:
    from app.core.db import SessionLocal
    from app.models import GmailIngestStatus
    from app.repositories.gmail_ingested_message import (
        GmailIngestedMessageRepository,
    )

    async with SessionLocal() as session:
        repo = GmailIngestedMessageRepository(session)
        claim = await repo.claim_or_skip(connection.id, "msg-1")
        assert claim is not None
        assert claim.ingest_status == GmailIngestStatus.CLAIMED


async def test_claim_or_skip_returns_none_for_already_completed(connection) -> None:
    from app.core.db import SessionLocal
    from app.models import GmailIngestStatus
    from app.repositories.gmail_ingested_message import (
        GmailIngestedMessageRepository,
    )

    async with SessionLocal() as session:
        await make_ingested_message(
            session,
            connection_id=connection.id,
            gmail_message_id="msg-done",
            status=GmailIngestStatus.COMPLETED,
        )
        claim = await GmailIngestedMessageRepository(session).claim_or_skip(
            connection.id, "msg-done"
        )
        assert claim is None


async def test_claim_or_skip_returns_none_for_failed(connection) -> None:
    from app.core.db import SessionLocal
    from app.models import GmailIngestStatus
    from app.repositories.gmail_ingested_message import (
        GmailIngestedMessageRepository,
    )

    async with SessionLocal() as session:
        await make_ingested_message(
            session,
            connection_id=connection.id,
            gmail_message_id="msg-failed",
            status=GmailIngestStatus.FAILED,
        )
        claim = await GmailIngestedMessageRepository(session).claim_or_skip(
            connection.id, "msg-failed"
        )
        assert claim is None


async def test_claim_or_skip_reclaims_reset_row(connection) -> None:
    from app.core.db import SessionLocal
    from app.models import GmailIngestStatus
    from app.repositories.gmail_ingested_message import (
        GmailIngestedMessageRepository,
    )

    async with SessionLocal() as session:
        await make_ingested_message(
            session,
            connection_id=connection.id,
            gmail_message_id="msg-reset",
            status=GmailIngestStatus.RESET,
        )
        claim = await GmailIngestedMessageRepository(session).claim_or_skip(
            connection.id, "msg-reset"
        )
        assert claim is not None
        assert claim.ingest_status == GmailIngestStatus.CLAIMED


async def test_reset_stale_claims_moves_old_claimed_rows_to_reset(connection) -> None:
    """Visibility timeout: rows stuck in 'claimed' past the deadline get recovered."""
    from sqlalchemy import update

    from app.core.db import SessionLocal
    from app.models import GmailIngestedMessage, GmailIngestStatus
    from app.repositories.gmail_ingested_message import (
        GmailIngestedMessageRepository,
    )

    async with SessionLocal() as session:
        row = await make_ingested_message(
            session,
            connection_id=connection.id,
            gmail_message_id="msg-stuck",
            status=GmailIngestStatus.CLAIMED,
        )

        # Backdate updated_at to simulate a stuck row.
        await session.execute(
            update(GmailIngestedMessage)
            .where(GmailIngestedMessage.id == row.id)
            .values(updated_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await session.commit()

        count = await GmailIngestedMessageRepository(session).reset_stale_claims(
            connection.id, timeout_minutes=15
        )
        assert count == 1

        await session.refresh(row)
        assert row.ingest_status == GmailIngestStatus.RESET


# ---------------------------------------------------------------------------
# Full sync path
# ---------------------------------------------------------------------------


def _mount_google_happy_path(respx_mock) -> None:
    """Shared respx setup: token refresh + list + get + attachment downloads."""
    respx_mock.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESPONSE)
    )
    respx_mock.get("https://gmail.googleapis.com/gmail/v1/users/me/messages").mock(
        return_value=httpx.Response(200, json=LIST_MESSAGES_RESPONSE)
    )
    respx_mock.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{MESSAGE_ID}"
    ).mock(return_value=httpx.Response(200, json=GET_MESSAGE_RESPONSE))
    respx_mock.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{MESSAGE_ID}"
        f"/attachments/{ATTACHMENT_PDF_1}"
    ).mock(
        return_value=httpx.Response(200, json=attachment_response(b"%PDF-1.4 resume 1"))
    )
    respx_mock.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{MESSAGE_ID}"
        f"/attachments/{ATTACHMENT_PDF_2}"
    ).mock(
        return_value=httpx.Response(200, json=attachment_response(b"%PDF-1.4 resume 2"))
    )
    # The image attachment would only be requested if we didn't filter
    # it out; route is defined to make the test fail loudly if we do.
    respx_mock.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{MESSAGE_ID}"
        f"/attachments/{ATTACHMENT_IMAGE}"
    ).mock(
        return_value=httpx.Response(200, json=attachment_response(b"should-not-fetch"))
    )


@respx.mock
async def test_sync_happy_path_ingests_eligible_attachments(
    connection, enqueued_tasks
) -> None:
    _mount_google_happy_path(respx.mock)

    from app.worker.tasks import _run_sync

    await _run_sync(connection.id)

    # Two PDF attachments ingested; the image was filtered out by
    # the narrower sync allowlist (PDF/DOCX/DOC only).
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models import Document, GmailIngestedMessage

    async with SessionLocal() as session:
        docs = (await session.execute(select(Document))).scalars().all()
        assert len(docs) == 2
        assert {d.filename for d in docs} == {"resume.pdf", "cover-letter.pdf"}

        claim = (await session.execute(select(GmailIngestedMessage))).scalar_one()
        assert claim.attachment_count == 2
        assert len(claim.document_ids) == 2

    # Extraction task was enqueued for each document.
    assert len(enqueued_tasks.for_task("extract_document_text")) == 2


@respx.mock
async def test_sync_dedups_on_rerun(connection, enqueued_tasks) -> None:
    _mount_google_happy_path(respx.mock)

    from app.worker.tasks import _run_sync

    await _run_sync(connection.id)
    first_enqueued = len(enqueued_tasks.for_task("extract_document_text"))
    assert first_enqueued == 2

    # Second run: same Google responses, but the ledger row is now
    # 'completed' so the message is skipped.
    await _run_sync(connection.id)

    assert len(enqueued_tasks.for_task("extract_document_text")) == first_enqueued


@respx.mock
async def test_sync_empty_inbox_produces_no_documents(
    connection, enqueued_tasks
) -> None:
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESPONSE)
    )
    respx.get("https://gmail.googleapis.com/gmail/v1/users/me/messages").mock(
        return_value=httpx.Response(200, json=LIST_MESSAGES_EMPTY)
    )

    from app.worker.tasks import _run_sync

    await _run_sync(connection.id)

    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.models import Document, GmailIngestedMessage

    async with SessionLocal() as session:
        doc_count = await session.scalar(select(func.count()).select_from(Document))
        ingest_count = await session.scalar(
            select(func.count()).select_from(GmailIngestedMessage)
        )

    assert doc_count == 0
    assert ingest_count == 0
    assert len(enqueued_tasks) == 0


# ---------------------------------------------------------------------------
# Auto-disconnect
# ---------------------------------------------------------------------------


@respx.mock
async def test_invalid_grant_auto_disconnects(connection, admin_user) -> None:
    """Revoked-at-source refresh token → connection deleted + activity logged."""
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )

    from app.worker.tasks import _run_sync

    await _run_sync(connection.id)

    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.models import ActivityAction, ActivityLog, GmailConnection

    async with SessionLocal() as session:
        connections = await session.scalar(
            select(func.count()).select_from(GmailConnection)
        )
        assert connections == 0

        log = (
            await session.execute(
                select(ActivityLog).where(
                    ActivityLog.action == ActivityAction.GMAIL_DISCONNECT
                )
            )
        ).scalar_one()
        assert log.actor_id == admin_user.id
        assert "auto-disconnected" in (log.detail or "")


# ---------------------------------------------------------------------------
# Auto-candidate hook
# ---------------------------------------------------------------------------


async def test_sync_candidate_service_creates_candidate_from_resume(
    admin_user,
) -> None:
    """Hook path: a RESUME-typed document yields exactly one candidate."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.core.db import sync_engine
    from app.models import Candidate, Document, DocumentStatus, DocumentType
    from app.services.sync_candidate_service import SyncCandidateService

    # Seed a ready resume document directly (skip the worker chain).
    with Session(sync_engine) as session:
        doc = Document(
            owner_id=admin_user.id,
            filename="resume.pdf",
            mime_type="application/pdf",
            size_bytes=1234,
            storage_key="key",
            status=DocumentStatus.READY,
            document_type=DocumentType.RESUME,
            metadata_={
                "name": "Ada Lovelace",
                "emails": ["ada@example.com"],
                "skills": ["python", "math"],
                "experience_years": 5,
            },
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        SyncCandidateService(session).handle_document_ready(doc)

        candidate = session.execute(
            select(Candidate).where(Candidate.source_document_id == doc.id)
        ).scalar_one()
        assert candidate.name == "Ada Lovelace"
        assert candidate.email == "ada@example.com"
        assert sorted(candidate.skills) == ["math", "python"]
        assert candidate.experience_years == 5


async def test_sync_candidate_service_is_idempotent(admin_user) -> None:
    """Calling the hook twice should update rather than duplicate."""
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from app.core.db import sync_engine
    from app.models import Candidate, Document, DocumentStatus, DocumentType
    from app.services.sync_candidate_service import SyncCandidateService

    with Session(sync_engine) as session:
        doc = Document(
            owner_id=admin_user.id,
            filename="cv.pdf",
            mime_type="application/pdf",
            size_bytes=1,
            storage_key="k",
            status=DocumentStatus.READY,
            document_type=DocumentType.RESUME,
            metadata_={"name": "A", "skills": ["python"]},
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        service = SyncCandidateService(session)
        service.handle_document_ready(doc)
        # Update the metadata and run again.
        doc.metadata_ = {**doc.metadata_, "name": "B", "skills": ["python", "rust"]}
        session.commit()
        service.handle_document_ready(doc)

        count = session.scalar(select(func.count()).select_from(Candidate))
        assert count == 1

        candidate = session.execute(select(Candidate)).scalar_one()
        assert candidate.name == "B"
        assert sorted(candidate.skills) == ["python", "rust"]


async def test_sync_candidate_service_ignores_non_resume(admin_user) -> None:
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from app.core.db import sync_engine
    from app.models import Candidate, Document, DocumentStatus, DocumentType
    from app.services.sync_candidate_service import SyncCandidateService

    with Session(sync_engine) as session:
        doc = Document(
            owner_id=admin_user.id,
            filename="contract.pdf",
            mime_type="application/pdf",
            size_bytes=1,
            storage_key="k",
            status=DocumentStatus.READY,
            document_type=DocumentType.CONTRACT,
            metadata_={"name": "N/A"},
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        SyncCandidateService(session).handle_document_ready(doc)

        count = session.scalar(select(func.count()).select_from(Candidate))
        assert count == 0
