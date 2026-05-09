"""F103.c — integration: portfolio uploaded before resume both end up
linked to the same candidate after the resume processes.

Exercises the chain ``SyncCandidateService.handle_document_ready``
→ deferred backfill → ``AuthorLinkageService.handle_document_ready``
without booting the full Celery worker. The chain mirrors what
``app.worker.tasks._on_ready_chain`` does in production.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import sync_engine
from app.models import Candidate, Document, DocumentStatus, DocumentType
from app.services.author_linkage_service import AuthorLinkageService
from app.services.sync_candidate_service import SyncCandidateService


def _seed_doc(
    session: Session,
    *,
    owner_id,
    filename: str,
    document_type: DocumentType,
    metadata: dict,
) -> Document:
    doc = Document(
        owner_id=owner_id,
        filename=filename,
        mime_type="application/pdf",
        size_bytes=1024,
        storage_key=f"key-{filename}",
        status=DocumentStatus.READY,
        document_type=document_type,
        metadata_=metadata,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def _on_ready(session: Session, doc: Document) -> None:
    """Production chain — keep order in sync with
    ``app.worker.tasks._on_ready_chain``."""
    SyncCandidateService(session).handle_document_ready(doc)
    AuthorLinkageService(session).handle_document_ready(doc)


@pytest.mark.asyncio
async def test_portfolio_first_then_resume(admin_user) -> None:
    with Session(sync_engine) as session:
        # 1. Portfolio uploaded first. No candidate exists yet — the
        #    linkage step finds no match, leaves authored_by_id NULL.
        portfolio = _seed_doc(
            session,
            owner_id=admin_user.id,
            filename="portfolio.pdf",
            document_type=DocumentType.OTHER,
            metadata={"emails": ["alice@example.com"]},
        )
        _on_ready(session, portfolio)
        session.refresh(portfolio)
        assert portfolio.authored_by_id is None

        # 2. Resume uploaded second. SyncCandidateService creates the
        #    candidate; the deferred backfill (called from
        #    SyncCandidate after commit) sweeps the portfolio. Then
        #    AuthorLinkageService links the resume to its own
        #    candidate.
        resume = _seed_doc(
            session,
            owner_id=admin_user.id,
            filename="alice_resume.pdf",
            document_type=DocumentType.RESUME,
            metadata={
                "name": "Alice Ng",
                "emails": ["alice@example.com"],
                "skills": ["python", "stripe"],
            },
        )
        _on_ready(session, resume)
        session.refresh(resume)
        session.refresh(portfolio)

        candidate = session.execute(
            select(Candidate).where(Candidate.email == "alice@example.com")
        ).scalar_one()

        # Both docs now point at the same candidate.
        assert resume.authored_by_id == candidate.id
        assert portfolio.authored_by_id == candidate.id

        # And from the candidate side, both docs surface in
        # ``authored_documents``.
        session.refresh(candidate)
        authored_ids = {d.id for d in candidate.authored_documents}
        assert {portfolio.id, resume.id} <= authored_ids


@pytest.mark.asyncio
async def test_re_running_chain_is_no_op(admin_user) -> None:
    """The chain is idempotent — running it twice on the same doc
    doesn't change anything (no duplicate candidates, no link
    overwrites)."""
    with Session(sync_engine) as session:
        resume = _seed_doc(
            session,
            owner_id=admin_user.id,
            filename="alice_resume.pdf",
            document_type=DocumentType.RESUME,
            metadata={
                "name": "Alice",
                "emails": ["alice@example.com"],
            },
        )
        _on_ready(session, resume)
        # Capture state.
        candidate_count_before = session.execute(
            select(Candidate).where(Candidate.owner_id == admin_user.id)
        ).all()

        _on_ready(session, resume)

        candidate_count_after = session.execute(
            select(Candidate).where(Candidate.owner_id == admin_user.id)
        ).all()
        assert len(candidate_count_before) == len(candidate_count_after)


@pytest.mark.asyncio
async def test_resume_only_owner_scoping(admin_user, hr_user) -> None:
    """If hr_user uploads a doc with admin_user's candidate's email,
    no cross-tenant link happens."""
    with Session(sync_engine) as session:
        admin_resume = _seed_doc(
            session,
            owner_id=admin_user.id,
            filename="admin_resume.pdf",
            document_type=DocumentType.RESUME,
            metadata={
                "name": "Admin Owner",
                "emails": ["admin-owner@example.com"],
            },
        )
        _on_ready(session, admin_resume)

        # hr_user uploads a portfolio that mentions admin_owner's
        # email — this could happen organically in any HR pool.
        hr_portfolio = _seed_doc(
            session,
            owner_id=hr_user.id,
            filename="hr_portfolio.pdf",
            document_type=DocumentType.OTHER,
            metadata={"emails": ["admin-owner@example.com"]},
        )
        _on_ready(session, hr_portfolio)
        session.refresh(hr_portfolio)
        assert hr_portfolio.authored_by_id is None
