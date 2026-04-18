"""F85: Postgres FTS integration tests.

Real Postgres, real generated tsvector column. These verify the
migration is wired correctly and that ``DocumentRepository.full_text_search``
ranks the way we expect.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.db import SessionLocal
from app.models import Document, DocumentStatus
from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository


async def _seed_doc(*, owner_id, filename: str, text: str) -> Document:
    async with SessionLocal() as session:
        doc = Document(
            owner_id=owner_id,
            filename=filename,
            mime_type="application/pdf",
            size_bytes=len(text),
            storage_key=f"test/{filename}-{uuid4()}",
            status=DocumentStatus.READY,
            extracted_text=text,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc


@pytest.fixture
async def owner_id():
    """A user row to satisfy documents.owner_id FK."""
    from app.adapters.argon2_hasher import Argon2Hasher
    from app.models import UserRole

    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.create(
            email=f"fts-{uuid4()}@test.hireflow.io",
            hashed_password=Argon2Hasher().hash("x"),
            full_name="FTS Tester",
            role=UserRole.HR,
        )
        return user.id


async def test_generated_tsvector_populates_on_insert(owner_id) -> None:
    """The migration's STORED generated column must auto-populate on insert."""
    doc = await _seed_doc(
        owner_id=owner_id,
        filename="resume.pdf",
        text="Senior Python engineer with Kubernetes and FastAPI experience.",
    )

    async with SessionLocal() as session:
        fresh = await session.get(Document, doc.id)
        assert fresh is not None
        # The tsvector is opaque to the ORM (we mapped it as str | None);
        # what matters is it's populated, not empty.
        assert fresh.extracted_text_tsv
        assert "python" in fresh.extracted_text_tsv.lower()


async def test_full_text_search_finds_single_word_query(owner_id) -> None:
    """The 'python -> 0 results' eval failure: lexical retrieval must catch this."""
    target = await _seed_doc(
        owner_id=owner_id,
        filename="python_dev.pdf",
        text="Python backend developer with five years of Django experience.",
    )
    await _seed_doc(
        owner_id=owner_id,
        filename="frontend_dev.pdf",
        text="React engineer building TypeScript SPAs and design systems.",
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.full_text_search("python", limit=10)

    hit_ids = [doc.id for doc, _ in hits]
    assert target.id in hit_ids
    # The unrelated doc must not show up (no overlap with "python").
    assert len(hit_ids) == 1


async def test_full_text_search_ranks_more_relevant_higher(owner_id) -> None:
    """ts_rank_cd should rank a doc with multiple term hits above one with a single hit."""
    strong = await _seed_doc(
        owner_id=owner_id,
        filename="strong.pdf",
        text="Python engineer. Python developer. Python expert. Python everywhere.",
    )
    weak = await _seed_doc(
        owner_id=owner_id,
        filename="weak.pdf",
        text="Java developer with one passing mention of python in side projects.",
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.full_text_search("python", limit=10)

    ranked = [doc.id for doc, _ in hits]
    assert ranked.index(strong.id) < ranked.index(weak.id)


async def test_full_text_search_excludes_non_ready_docs(owner_id) -> None:
    """Pending/processing/failed docs must not surface in search results."""
    pending = await _seed_doc(
        owner_id=owner_id,
        filename="pending.pdf",
        text="Python engineer resume but still being processed.",
    )

    async with SessionLocal() as session:
        # Demote the doc out of READY.
        fresh = await session.get(Document, pending.id)
        assert fresh is not None
        fresh.status = DocumentStatus.PROCESSING
        await session.commit()

        repo = DocumentRepository(session)
        hits = await repo.full_text_search("python", limit=10)

    assert pending.id not in [doc.id for doc, _ in hits]


async def test_full_text_search_empty_query_returns_empty(owner_id) -> None:
    await _seed_doc(
        owner_id=owner_id,
        filename="any.pdf",
        text="Some content here that contains words.",
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        assert await repo.full_text_search("", limit=10) == []
        assert await repo.full_text_search("   ", limit=10) == []


async def test_full_text_search_handles_multiword_query(owner_id) -> None:
    """plainto_tsquery joins terms with AND — both must appear."""
    both = await _seed_doc(
        owner_id=owner_id,
        filename="both.pdf",
        text="Senior Python engineer with Kubernetes operator experience.",
    )
    only_one = await _seed_doc(
        owner_id=owner_id,
        filename="only_one.pdf",
        text="Senior Java engineer, no container experience.",
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.full_text_search("python kubernetes", limit=10)

    hit_ids = [doc.id for doc, _ in hits]
    assert both.id in hit_ids
    assert only_one.id not in hit_ids
