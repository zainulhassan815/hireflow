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
        assert fresh.search_tsv
        assert "python" in fresh.search_tsv.lower()
        # F87: filename indexed at weight A → its tokens carry an :A
        # suffix in the textual tsvector representation.
        assert "resum" in fresh.search_tsv.lower()  # filename "resume.pdf"


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


# ---------------------------------------------------------------------------
# F86 ownership scoping
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# F87 multi-field weighted FTS
# ---------------------------------------------------------------------------


async def test_filename_match_outranks_body_only_match(owner_id) -> None:
    """Filename indexed at weight A; body at weight C. ts_rank_cd must reflect that."""
    title_match = await _seed_doc(
        owner_id=owner_id,
        filename="menu_analyzer_portfolio.pdf",
        text="Some completely unrelated paragraph about cats and dogs.",
    )
    body_match = await _seed_doc(
        owner_id=owner_id,
        filename="random_filename.pdf",
        # Body mentions menu analyzer but the filename does not.
        text=(
            "This document is a portfolio piece. The menu analyzer was "
            "built for restaurants. The menu analyzer reads images and "
            "returns nutritional info."
        ),
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.full_text_search("menu analyzer", limit=10)

    ranked = [doc.id for doc, _ in hits]
    assert title_match.id in ranked
    assert body_match.id in ranked
    # Title match must outrank body-only match.
    assert ranked.index(title_match.id) < ranked.index(body_match.id)


async def test_skills_metadata_match_contributes_to_ranking(owner_id) -> None:
    """Skills indexed at weight B should outrank a body-only mention."""
    skills_doc = await _seed_doc(
        owner_id=owner_id,
        filename="resume_a.pdf",
        text="Generic engineer profile with various accomplishments.",
    )
    body_doc = await _seed_doc(
        owner_id=owner_id,
        filename="resume_b.pdf",
        text=(
            "Engineer profile. Has used kubernetes once briefly. "
            "Other unrelated content here."
        ),
    )

    # Patch metadata.skills on skills_doc to include "kubernetes".
    async with SessionLocal() as session:
        fresh = await session.get(Document, skills_doc.id)
        assert fresh is not None
        fresh.metadata_ = {"skills": ["kubernetes", "python"]}
        await session.commit()

        repo = DocumentRepository(session)
        hits = await repo.full_text_search("kubernetes", limit=10)

    ranked = [doc.id for doc, _ in hits]
    assert skills_doc.id in ranked
    assert body_doc.id in ranked
    # Skills (weight B) > body (weight C).
    assert ranked.index(skills_doc.id) < ranked.index(body_doc.id)


async def test_filename_only_match_when_body_has_no_overlap(owner_id) -> None:
    """A doc with the term only in the filename must still surface."""
    doc = await _seed_doc(
        owner_id=owner_id,
        filename="quarterly_telemedicine_review.pdf",
        text="Lorem ipsum dolor sit amet — body has no matching term.",
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.full_text_search("telemedicine", limit=10)

    assert doc.id in [d.id for d, _ in hits]


async def test_full_text_search_scopes_to_owner(owner_id) -> None:
    """A user must not see documents owned by someone else."""
    from app.adapters.argon2_hasher import Argon2Hasher
    from app.models import UserRole

    # Two users; each owns one Python resume.
    async with SessionLocal() as session:
        other = await UserRepository(session).create(
            email=f"other-{uuid4()}@test.hireflow.io",
            hashed_password=Argon2Hasher().hash("x"),
            full_name="Other Owner",
            role=UserRole.HR,
        )
        other_id = other.id

    mine = await _seed_doc(
        owner_id=owner_id,
        filename="mine.pdf",
        text="Python engineer resume — MINE.",
    )
    theirs = await _seed_doc(
        owner_id=other_id,
        filename="theirs.pdf",
        text="Python engineer resume — THEIRS.",
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)

        mine_only = await repo.full_text_search("python", limit=10, owner_id=owner_id)
        their_only = await repo.full_text_search("python", limit=10, owner_id=other_id)
        unscoped = await repo.full_text_search("python", limit=10)

    assert [d.id for d, _ in mine_only] == [mine.id]
    assert [d.id for d, _ in their_only] == [theirs.id]
    # Unscoped (admin) sees both.
    assert {d.id for d, _ in unscoped} == {mine.id, theirs.id}
