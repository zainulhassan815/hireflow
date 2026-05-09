"""Tests for ``AuthorLinkageService`` (F103.c).

Covers:
- ingest-time inference from ``metadata.emails``
- owner scoping
- multi-email + multi-candidate disambiguation
- idempotency (never overwrites an existing FK)
- case insensitivity
- deferred backfill when a candidate is created late
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.db import sync_engine
from app.models import (
    AuthorSource,
    Candidate,
    Document,
    DocumentStatus,
    DocumentType,
)
from app.services.author_linkage_service import AuthorLinkageService


def _seed_doc(
    session: Session,
    *,
    owner_id,
    filename: str = "doc.pdf",
    document_type: DocumentType | None = DocumentType.OTHER,
    emails: list[str] | None = None,
    authored_by_id=None,
    authored_by_source: AuthorSource | None = None,
) -> Document:
    metadata = {"emails": emails} if emails is not None else None
    doc = Document(
        owner_id=owner_id,
        filename=filename,
        mime_type="application/pdf",
        size_bytes=1024,
        storage_key=f"key-{filename}",
        status=DocumentStatus.READY,
        document_type=document_type,
        metadata_=metadata,
        authored_by_id=authored_by_id,
        authored_by_source=authored_by_source,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def _seed_candidate(
    session: Session,
    *,
    owner_id,
    email: str | None,
    name: str = "Test Candidate",
    source_document_id=None,
) -> Candidate:
    candidate = Candidate(
        owner_id=owner_id,
        name=name,
        email=email,
        source_document_id=source_document_id,
    )
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


@pytest.mark.asyncio
async def test_email_match_links_doc_to_candidate(admin_user) -> None:
    with Session(sync_engine) as session:
        candidate = _seed_candidate(
            session, owner_id=admin_user.id, email="alice@example.com"
        )
        doc = _seed_doc(session, owner_id=admin_user.id, emails=["alice@example.com"])

        AuthorLinkageService(session).handle_document_ready(doc)

        session.refresh(doc)
        assert doc.authored_by_id == candidate.id


@pytest.mark.asyncio
async def test_no_emails_no_link(admin_user) -> None:
    with Session(sync_engine) as session:
        _seed_candidate(session, owner_id=admin_user.id, email="alice@example.com")
        doc = _seed_doc(session, owner_id=admin_user.id, emails=None)

        AuthorLinkageService(session).handle_document_ready(doc)

        session.refresh(doc)
        assert doc.authored_by_id is None


@pytest.mark.asyncio
async def test_owner_scoped_match(admin_user, hr_user) -> None:
    """Email match must not cross owners — HR users are tenants."""
    with Session(sync_engine) as session:
        # Candidate belongs to admin_user.
        _seed_candidate(session, owner_id=admin_user.id, email="alice@example.com")
        # Doc belongs to hr_user; same email but different owner.
        doc = _seed_doc(session, owner_id=hr_user.id, emails=["alice@example.com"])

        AuthorLinkageService(session).handle_document_ready(doc)

        session.refresh(doc)
        assert doc.authored_by_id is None


@pytest.mark.asyncio
async def test_idempotent_never_overwrites(admin_user) -> None:
    """Calling twice on an already-linked doc is a no-op."""
    with Session(sync_engine) as session:
        first = _seed_candidate(
            session, owner_id=admin_user.id, email="alice@example.com"
        )
        # Pre-link the doc to the first candidate.
        doc = _seed_doc(
            session,
            owner_id=admin_user.id,
            emails=["alice@example.com", "bob@example.com"],
            authored_by_id=first.id,
        )
        # A second candidate also matches one of the emails.
        _seed_candidate(
            session,
            owner_id=admin_user.id,
            email="bob@example.com",
            name="Bob",
        )

        AuthorLinkageService(session).handle_document_ready(doc)

        session.refresh(doc)
        # Pre-existing FK must not be replaced.
        assert doc.authored_by_id == first.id


@pytest.mark.asyncio
async def test_case_insensitive_match(admin_user) -> None:
    """Candidate.email may be mixed-case (legacy data); the matcher
    lowercases on both sides."""
    with Session(sync_engine) as session:
        candidate = _seed_candidate(
            session, owner_id=admin_user.id, email="Alice@Example.COM"
        )
        # ``metadata.emails`` is lowercased by the F103.c classifier
        # change; defend against legacy callers anyway by running the
        # match with mixed case here too.
        doc = _seed_doc(session, owner_id=admin_user.id, emails=["alice@example.com"])

        AuthorLinkageService(session).handle_document_ready(doc)

        session.refresh(doc)
        assert doc.authored_by_id == candidate.id


@pytest.mark.asyncio
async def test_multi_candidate_match_picks_first_logs_warning(
    admin_user, caplog
) -> None:
    with Session(sync_engine) as session:
        a = _seed_candidate(
            session, owner_id=admin_user.id, email="alice@example.com", name="Alice"
        )
        b = _seed_candidate(
            session, owner_id=admin_user.id, email="bob@example.com", name="Bob"
        )
        # Doc lists both emails — both candidates match.
        doc = _seed_doc(
            session,
            owner_id=admin_user.id,
            emails=["alice@example.com", "bob@example.com"],
        )

        with caplog.at_level("WARNING", logger="app.services.author_linkage_service"):
            AuthorLinkageService(session).handle_document_ready(doc)

        session.refresh(doc)
        assert doc.authored_by_id in {a.id, b.id}
        assert any("multiple candidates" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_backfill_for_candidate_links_prior_unlinked_docs(admin_user) -> None:
    """Common case: portfolio uploaded first, resume after."""
    with Session(sync_engine) as session:
        # Portfolio ingested before any candidate exists — its emails
        # are recorded but no FK gets set.
        portfolio = _seed_doc(
            session,
            owner_id=admin_user.id,
            filename="portfolio.pdf",
            emails=["alice@example.com"],
        )
        case_study = _seed_doc(
            session,
            owner_id=admin_user.id,
            filename="case_study.pdf",
            emails=["alice@example.com", "noreply@example.com"],
        )
        # Unrelated doc owned by the same user — must NOT be linked.
        unrelated = _seed_doc(
            session,
            owner_id=admin_user.id,
            filename="unrelated.pdf",
            emails=["someone@elsewhere.io"],
        )

        # Now create the candidate.
        candidate = _seed_candidate(
            session, owner_id=admin_user.id, email="alice@example.com"
        )
        linked = AuthorLinkageService(session).backfill_for_candidate(candidate)

        assert linked == 2

        for doc, expected in (
            (portfolio, candidate.id),
            (case_study, candidate.id),
            (unrelated, None),
        ):
            session.refresh(doc)
            assert doc.authored_by_id == expected, doc.filename


@pytest.mark.asyncio
async def test_backfill_idempotent(admin_user) -> None:
    with Session(sync_engine) as session:
        candidate = _seed_candidate(
            session, owner_id=admin_user.id, email="alice@example.com"
        )
        _seed_doc(
            session,
            owner_id=admin_user.id,
            emails=["alice@example.com"],
            authored_by_id=candidate.id,
        )

        # Second call — already linked, nothing to do.
        linked = AuthorLinkageService(session).backfill_for_candidate(candidate)
        assert linked == 0


@pytest.mark.asyncio
async def test_backfill_no_candidate_email(admin_user) -> None:
    """Defensive: candidate without an email shouldn't raise; nothing
    to match against."""
    with Session(sync_engine) as session:
        candidate = _seed_candidate(
            session, owner_id=admin_user.id, email=None, name="Anonymous"
        )
        linked = AuthorLinkageService(session).backfill_for_candidate(candidate)
        assert linked == 0


@pytest.mark.asyncio
async def test_handle_document_ready_swallows_exceptions(
    admin_user, monkeypatch
) -> None:
    """Contract: linkage failure must not roll back extraction. Same
    promise ``SyncCandidateService.handle_document_ready`` makes."""
    with Session(sync_engine) as session:
        doc = _seed_doc(session, owner_id=admin_user.id, emails=["alice@example.com"])

        service = AuthorLinkageService(session)

        def boom(*args, **kwargs):
            raise RuntimeError("simulated infra failure")

        monkeypatch.setattr(service, "_link_if_match", boom)

        # Should not raise.
        service.handle_document_ready(doc)


@pytest.mark.asyncio
async def test_resume_self_link_via_email(admin_user) -> None:
    """A resume's own email matches the candidate created from it."""
    with Session(sync_engine) as session:
        resume = _seed_doc(
            session,
            owner_id=admin_user.id,
            filename="alice_resume.pdf",
            document_type=DocumentType.RESUME,
            emails=["alice@example.com"],
        )
        candidate = _seed_candidate(
            session,
            owner_id=admin_user.id,
            email="alice@example.com",
            source_document_id=resume.id,
        )

        AuthorLinkageService(session).handle_document_ready(resume)

        session.refresh(resume)
        assert resume.authored_by_id == candidate.id

        # And the candidate's authored_documents now reaches the resume.
        session.refresh(candidate)
        authored_ids = {d.id for d in candidate.authored_documents}
        assert resume.id in authored_ids


# ---------- F103.c.2: source flag + manual-skip ----------


@pytest.mark.asyncio
async def test_email_match_stamps_email_match_source(admin_user) -> None:
    """F103.c.2 — handle_document_ready stamps
    ``authored_by_source = 'email_match'`` so the F103.c.2 PATCH
    route can later detect the link as inferred."""
    with Session(sync_engine) as session:
        candidate = _seed_candidate(
            session, owner_id=admin_user.id, email="alice@example.com"
        )
        doc = _seed_doc(session, owner_id=admin_user.id, emails=["alice@example.com"])

        AuthorLinkageService(session).handle_document_ready(doc)

        session.refresh(doc)
        assert doc.authored_by_id == candidate.id
        assert doc.authored_by_source == AuthorSource.EMAIL_MATCH


@pytest.mark.asyncio
async def test_link_if_match_skips_dangling_manual_source(admin_user) -> None:
    """F103.c.2 dangling-source case: candidate deleted via
    ON DELETE SET NULL leaves ``authored_by_id`` NULL but
    ``authored_by_source`` still 'manual'. The operator's intent
    was specific to the deleted candidate; auto-relinking to a
    different candidate via a fresh email match would silently
    undo that intent. Skip."""
    with Session(sync_engine) as session:
        # Seed a doc that's been "manually linked, candidate deleted":
        # FK NULL, source MANUAL.
        doc = _seed_doc(
            session,
            owner_id=admin_user.id,
            emails=["alice@example.com"],
            authored_by_id=None,
            authored_by_source=AuthorSource.MANUAL,
        )
        # New candidate appears with the same email.
        new_candidate = _seed_candidate(
            session, owner_id=admin_user.id, email="alice@example.com"
        )

        AuthorLinkageService(session).handle_document_ready(doc)

        session.refresh(doc)
        # FK stays NULL; source stays manual; the new candidate is
        # NOT auto-linked.
        assert doc.authored_by_id is None
        assert doc.authored_by_source == AuthorSource.MANUAL
        # Belt-and-suspenders: the new candidate has no
        # authored_documents.
        session.refresh(new_candidate)
        assert list(new_candidate.authored_documents) == []


@pytest.mark.asyncio
async def test_backfill_for_candidate_skips_dangling_manual_source(admin_user) -> None:
    """Same dangling-source story for the deferred-resolution path."""
    with Session(sync_engine) as session:
        doc = _seed_doc(
            session,
            owner_id=admin_user.id,
            emails=["alice@example.com"],
            authored_by_id=None,
            authored_by_source=AuthorSource.MANUAL,
        )
        new_candidate = _seed_candidate(
            session, owner_id=admin_user.id, email="alice@example.com"
        )

        linked = AuthorLinkageService(session).backfill_for_candidate(new_candidate)
        assert linked == 0

        session.refresh(doc)
        assert doc.authored_by_id is None
        assert doc.authored_by_source == AuthorSource.MANUAL


@pytest.mark.asyncio
async def test_backfill_for_candidate_stamps_email_match_source(
    admin_user,
) -> None:
    """F103.c.2 — when the deferred backfill links a doc, it stamps
    the source so the manual-override route can later detect it."""
    with Session(sync_engine) as session:
        doc = _seed_doc(session, owner_id=admin_user.id, emails=["alice@example.com"])
        candidate = _seed_candidate(
            session, owner_id=admin_user.id, email="alice@example.com"
        )

        linked = AuthorLinkageService(session).backfill_for_candidate(candidate)
        assert linked == 1

        session.refresh(doc)
        assert doc.authored_by_id == candidate.id
        assert doc.authored_by_source == AuthorSource.EMAIL_MATCH
