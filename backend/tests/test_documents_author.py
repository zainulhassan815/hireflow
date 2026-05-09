"""F103.c.2 — PATCH /documents/{id}/author route tests.

Exercises the HTTP surface end-to-end: auth, owner scoping, the
candidate cross-tenant 404, idempotency, and the activity-log +
Celery-enqueue side effects. The Celery task is patched so the
test doesn't need a worker running.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import (
    ActivityLog,
    AuthorSource,
    Candidate,
    Document,
    DocumentStatus,
    DocumentType,
)


async def _seed_doc(
    *,
    owner_id: UUID,
    filename: str = "case_study.pdf",
    document_type: DocumentType = DocumentType.OTHER,
    authored_by_id: UUID | None = None,
    authored_by_source: AuthorSource | None = None,
) -> Document:
    async with SessionLocal() as session:
        doc = Document(
            owner_id=owner_id,
            filename=filename,
            mime_type="application/pdf",
            size_bytes=100,
            storage_key=f"test/{filename}-{uuid4()}",
            status=DocumentStatus.READY,
            document_type=document_type,
            authored_by_id=authored_by_id,
            authored_by_source=authored_by_source,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc


async def _seed_candidate(
    *, owner_id: UUID, name: str = "Alice Ng", email: str = "alice@example.com"
) -> Candidate:
    async with SessionLocal() as session:
        cand = Candidate(owner_id=owner_id, name=name, email=email)
        session.add(cand)
        await session.commit()
        await session.refresh(cand)
        return cand


@pytest.fixture
def reembed_spy(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Capture ``reembed_document.delay(...)`` calls without a worker."""
    spy = MagicMock()
    monkeypatch.setattr(
        "app.api.routes.documents.reembed_document",
        MagicMock(delay=spy),
    )
    return spy


# ---------- auth + owner scoping ----------


async def test_unauthenticated_rejected(client) -> None:
    response = await client.patch(
        f"/api/documents/{uuid4()}/author",
        json={"candidate_id": str(uuid4())},
    )
    assert response.status_code == 401


async def test_404_when_document_missing(
    client, hr_user, hr_token, auth_headers, reembed_spy
) -> None:
    response = await client.patch(
        f"/api/documents/{uuid4()}/author",
        json={"candidate_id": None},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 404
    reembed_spy.assert_not_called()


async def test_403_when_other_owners_document(
    client, hr_user, hr_token, auth_headers, admin_user, reembed_spy
) -> None:
    """HR PATCHing another user's doc → 403 (the doc-side
    ``_ensure_access`` enforces this; we surface 403 not 404 here
    because the document exists, just not for this caller)."""
    other_doc = await _seed_doc(owner_id=admin_user.id)
    other_candidate = await _seed_candidate(owner_id=admin_user.id)

    response = await client.patch(
        f"/api/documents/{other_doc.id}/author",
        json={"candidate_id": str(other_candidate.id)},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 403
    reembed_spy.assert_not_called()


async def test_404_when_candidate_belongs_to_another_owner(
    client, hr_user, hr_token, auth_headers, admin_user, reembed_spy
) -> None:
    """Cross-tenant candidate id → 404. Same shape as 'candidate
    missing' so the existence side-channel stays closed."""
    own_doc = await _seed_doc(owner_id=hr_user.id)
    foreign_candidate = await _seed_candidate(owner_id=admin_user.id)

    response = await client.patch(
        f"/api/documents/{own_doc.id}/author",
        json={"candidate_id": str(foreign_candidate.id)},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 404
    reembed_spy.assert_not_called()


# ---------- happy paths ----------


async def test_set_author_writes_fk_and_source_and_enqueues_reembed(
    client, hr_user, hr_token, auth_headers, reembed_spy
) -> None:
    doc = await _seed_doc(owner_id=hr_user.id)
    candidate = await _seed_candidate(owner_id=hr_user.id)

    response = await client.patch(
        f"/api/documents/{doc.id}/author",
        json={"candidate_id": str(candidate.id)},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["authored_by_id"] == str(candidate.id)
    assert body["authored_by_source"] == "manual"
    assert body["authored_by"]["id"] == str(candidate.id)
    assert body["authored_by"]["name"] == "Alice Ng"

    # DB state.
    async with SessionLocal() as session:
        fresh = await session.get(Document, doc.id)
        assert fresh.authored_by_id == candidate.id
        assert fresh.authored_by_source == AuthorSource.MANUAL

    # Celery enqueue.
    reembed_spy.assert_called_once_with(str(doc.id))


async def test_clear_author_nulls_fk_and_source(
    client, hr_user, hr_token, auth_headers, reembed_spy
) -> None:
    candidate = await _seed_candidate(owner_id=hr_user.id)
    doc = await _seed_doc(
        owner_id=hr_user.id,
        authored_by_id=candidate.id,
        authored_by_source=AuthorSource.EMAIL_MATCH,
    )

    response = await client.patch(
        f"/api/documents/{doc.id}/author",
        json={"candidate_id": None},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["authored_by_id"] is None
    assert body["authored_by_source"] is None
    assert body["authored_by"] is None

    async with SessionLocal() as session:
        fresh = await session.get(Document, doc.id)
        assert fresh.authored_by_id is None
        assert fresh.authored_by_source is None

    reembed_spy.assert_called_once_with(str(doc.id))


async def test_email_match_to_manual_is_a_change(
    client, hr_user, hr_token, auth_headers, reembed_spy
) -> None:
    """Re-PATCH-ing the same candidate after an email-match auto-
    link still flips the source to 'manual' — that's a meaningful
    state change the audit trail wants to record."""
    candidate = await _seed_candidate(owner_id=hr_user.id)
    doc = await _seed_doc(
        owner_id=hr_user.id,
        authored_by_id=candidate.id,
        authored_by_source=AuthorSource.EMAIL_MATCH,
    )

    response = await client.patch(
        f"/api/documents/{doc.id}/author",
        json={"candidate_id": str(candidate.id)},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200
    assert response.json()["authored_by_source"] == "manual"
    reembed_spy.assert_called_once()


# ---------- idempotency ----------


async def test_no_op_when_state_already_matches(
    client, hr_user, hr_token, auth_headers, reembed_spy
) -> None:
    """PATCH with the same (candidate_id, source=manual) state →
    no re-embed enqueue, no activity log write."""
    candidate = await _seed_candidate(owner_id=hr_user.id)
    doc = await _seed_doc(
        owner_id=hr_user.id,
        authored_by_id=candidate.id,
        authored_by_source=AuthorSource.MANUAL,
    )

    response = await client.patch(
        f"/api/documents/{doc.id}/author",
        json={"candidate_id": str(candidate.id)},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200
    reembed_spy.assert_not_called()

    # No activity-log row was written.
    async with SessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(ActivityLog).where(
                        ActivityLog.resource_id == str(doc.id),
                        ActivityLog.action == "document_author_set",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert rows == []


async def test_no_op_clear_when_already_unlinked(
    client, hr_user, hr_token, auth_headers, reembed_spy
) -> None:
    doc = await _seed_doc(owner_id=hr_user.id)

    response = await client.patch(
        f"/api/documents/{doc.id}/author",
        json={"candidate_id": None},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200
    reembed_spy.assert_not_called()


# ---------- activity log ----------


async def test_set_author_writes_activity_log(
    client, hr_user, hr_token, auth_headers, reembed_spy
) -> None:
    doc = await _seed_doc(owner_id=hr_user.id)
    candidate = await _seed_candidate(owner_id=hr_user.id)

    await client.patch(
        f"/api/documents/{doc.id}/author",
        json={"candidate_id": str(candidate.id)},
        headers=auth_headers(hr_token),
    )

    async with SessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(ActivityLog).where(
                        ActivityLog.resource_id == str(doc.id),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].action.value == "document_author_set"
        assert rows[0].actor_id == hr_user.id
        assert rows[0].resource_type == "document"


async def test_clear_author_writes_activity_log(
    client, hr_user, hr_token, auth_headers, reembed_spy
) -> None:
    candidate = await _seed_candidate(owner_id=hr_user.id)
    doc = await _seed_doc(
        owner_id=hr_user.id,
        authored_by_id=candidate.id,
        authored_by_source=AuthorSource.EMAIL_MATCH,
    )

    await client.patch(
        f"/api/documents/{doc.id}/author",
        json={"candidate_id": None},
        headers=auth_headers(hr_token),
    )

    async with SessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(ActivityLog).where(
                        ActivityLog.resource_id == str(doc.id),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].action.value == "document_author_cleared"
