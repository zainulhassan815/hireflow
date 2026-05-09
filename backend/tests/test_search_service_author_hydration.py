"""F103.c — chunk hydration carries author attribution.

Two paths feed ``RetrievedChunk.authored_by_name``:

1. ``Document.authored_by_id`` set explicitly (the
   ``AuthorLinkageService`` happy path).
2. Resume self-link fallback: ``authored_by_id`` is NULL but the
   document's a resume, and a candidate row points at it via
   ``Candidate.source_document_id``. Belt-and-suspenders for the
   rare race where the linkage step never ran.

These tests target ``DocumentRepository.find_resume_authors``
directly because it's the seam where the fallback lookup happens —
exercising the full ``retrieve_chunks`` pipeline would require
stubbing the vector store + reranker, which doesn't add coverage
beyond what the unit-level test gives.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.db import SessionLocal
from app.models import Candidate, Document, DocumentStatus, DocumentType
from app.repositories.document import DocumentRepository


async def _seed_doc(
    session,
    *,
    owner_id,
    document_type: DocumentType = DocumentType.RESUME,
    filename: str = "doc.pdf",
) -> Document:
    doc = Document(
        owner_id=owner_id,
        filename=filename,
        mime_type="application/pdf",
        size_bytes=100,
        storage_key=f"key-{uuid4()}",
        status=DocumentStatus.READY,
        document_type=document_type,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


@pytest.mark.asyncio
async def test_find_resume_authors_returns_candidate_per_doc(admin_user) -> None:
    async with SessionLocal() as session:
        resume_a = await _seed_doc(
            session, owner_id=admin_user.id, filename="alice_resume.pdf"
        )
        resume_b = await _seed_doc(
            session, owner_id=admin_user.id, filename="bob_resume.pdf"
        )
        # Candidate A points at resume_a; B at resume_b.
        cand_a = Candidate(
            owner_id=admin_user.id,
            name="Alice Ng",
            email="alice@example.com",
            source_document_id=resume_a.id,
        )
        cand_b = Candidate(
            owner_id=admin_user.id,
            name="Bob",
            email="bob@example.com",
            source_document_id=resume_b.id,
        )
        session.add_all([cand_a, cand_b])
        await session.commit()
        await session.refresh(cand_a)
        await session.refresh(cand_b)

        repo = DocumentRepository(session)
        authors = await repo.find_resume_authors([resume_a.id, resume_b.id])

        assert authors[resume_a.id].id == cand_a.id
        assert authors[resume_a.id].name == "Alice Ng"
        assert authors[resume_b.id].id == cand_b.id


@pytest.mark.asyncio
async def test_find_resume_authors_skips_unlinked(admin_user) -> None:
    """A resume with no candidate pointing at it returns nothing — the
    caller treats missing entries as 'no author'."""
    async with SessionLocal() as session:
        orphan = await _seed_doc(session, owner_id=admin_user.id)

        repo = DocumentRepository(session)
        authors = await repo.find_resume_authors([orphan.id])

        assert authors == {}


@pytest.mark.asyncio
async def test_find_resume_authors_empty_input() -> None:
    """Defensive: empty list short-circuits without a query."""
    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        assert await repo.find_resume_authors([]) == {}


@pytest.mark.asyncio
async def test_authored_documents_relationship_back_populates(admin_user) -> None:
    """End-to-end: setting ``Document.authored_by_id`` makes the doc
    show up under ``Candidate.authored_documents``. Catches relationship
    misconfiguration."""
    async with SessionLocal() as session:
        candidate = Candidate(
            owner_id=admin_user.id,
            name="Alice",
            email="alice@example.com",
        )
        session.add(candidate)
        await session.commit()
        await session.refresh(candidate)

        portfolio = await _seed_doc(
            session,
            owner_id=admin_user.id,
            document_type=DocumentType.OTHER,
            filename="portfolio.pdf",
        )
        portfolio.authored_by_id = candidate.id
        await session.commit()
        await session.refresh(candidate)
        await session.refresh(portfolio)

        # Forward edge.
        assert portfolio.authored_by is not None
        assert portfolio.authored_by.id == candidate.id

        # Back edge.
        assert any(d.id == portfolio.id for d in candidate.authored_documents)
