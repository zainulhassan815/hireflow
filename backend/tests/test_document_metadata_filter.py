"""F89.a.1 — DocumentRepository.search_by_metadata hardening tests.

Verifies the two corrections F89.a.1 applies:

1. **Skill filter uses JSONB containment**, not substring ILIKE.
   Substring matching would incorrectly pair "python" with
   "pythonic"/"jython"/"python3" — false positives that become more
   likely as the skill vocabulary grows.
2. **Experience-years integer cast is guarded by ``jsonb_typeof =
   'number'``**. Malformed values (string "5+", lists, bools) no
   longer crash the query with a 500 — the row is filtered out
   cleanly.

Real Postgres, via the existing session fixture pattern used by
``test_document_fts.py``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.db import SessionLocal
from app.models import Document, DocumentStatus, DocumentType
from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository


async def _seed_doc(
    *,
    owner_id,
    filename: str,
    metadata: dict | None = None,
) -> Document:
    async with SessionLocal() as session:
        doc = Document(
            owner_id=owner_id,
            filename=filename,
            mime_type="application/pdf",
            size_bytes=100,
            storage_key=f"test/{filename}-{uuid4()}",
            status=DocumentStatus.READY,
            document_type=DocumentType.RESUME,
            metadata_=metadata or {},
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc


@pytest.fixture
async def owner_id():
    from app.adapters.argon2_hasher import Argon2Hasher
    from app.models import UserRole

    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.create(
            email=f"metafilter-{uuid4()}@test.hireflow.io",
            hashed_password=Argon2Hasher().hash("x"),
            full_name="Meta Filter Tester",
            role=UserRole.HR,
        )
        return user.id


# ---------------------------------------------------------------------------
# Skills — JSONB containment semantics
# ---------------------------------------------------------------------------


async def test_skill_filter_uses_exact_membership_not_substring(
    owner_id,
) -> None:
    """F89.a.1 motivation: the old ``astext ILIKE '%python%'`` shape
    matched "pythonic" too. Exact containment must reject it."""
    python_doc = await _seed_doc(
        owner_id=owner_id,
        filename="real_python.pdf",
        metadata={"skills": ["python", "aws"]},
    )
    pythonic_doc = await _seed_doc(
        owner_id=owner_id,
        filename="pythonic_coder.pdf",
        metadata={"skills": ["pythonic", "kubernetes"]},
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.search_by_metadata(skills=["python"], owner_id=owner_id)

    ids = {h.id for h in hits}
    assert python_doc.id in ids
    assert pythonic_doc.id not in ids, (
        "substring false positive regression: 'python' filter matched "
        "a doc whose only skill is 'pythonic'"
    )


async def test_skill_filter_multiple_required_all_present(owner_id) -> None:
    """Multi-skill queries use AND — every requested skill must
    appear. Preserves existing semantics."""
    has_both = await _seed_doc(
        owner_id=owner_id,
        filename="full_stack.pdf",
        metadata={"skills": ["python", "aws", "react"]},
    )
    has_one = await _seed_doc(
        owner_id=owner_id,
        filename="python_only.pdf",
        metadata={"skills": ["python"]},
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.search_by_metadata(
            skills=["python", "aws"], owner_id=owner_id
        )

    ids = {h.id for h in hits}
    assert has_both.id in ids
    assert has_one.id not in ids


async def test_skill_filter_lowercase_normalization(owner_id) -> None:
    """Parser emits lowercase; classifier stores lowercase. The repo
    defensively lowercases too so a caller passing mixed case still
    works."""
    doc = await _seed_doc(
        owner_id=owner_id,
        filename="mixed_case_query.pdf",
        metadata={"skills": ["python"]},
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.search_by_metadata(
            skills=["Python"],  # caller-side mixed case
            owner_id=owner_id,
        )

    assert doc.id in {h.id for h in hits}


async def test_empty_skill_string_is_ignored(owner_id) -> None:
    """Defensive guard against ``skills=[""]`` — would otherwise
    produce ``@> [""]`` which is a no-op filter. Skip whitespace-only
    entries."""
    doc = await _seed_doc(
        owner_id=owner_id,
        filename="any_skills.pdf",
        metadata={"skills": ["python"]},
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        # empty skill should be dropped; python filter still applies
        hits = await repo.search_by_metadata(
            skills=["", "python", "   "], owner_id=owner_id
        )

    assert doc.id in {h.id for h in hits}


async def test_missing_skills_metadata_excludes_row(owner_id) -> None:
    """Docs with no ``skills`` key in metadata can't match a skill
    filter — ``NULL @> [...]`` is UNKNOWN → excluded."""
    no_skills_doc = await _seed_doc(
        owner_id=owner_id,
        filename="no_metadata.pdf",
        metadata={},  # no skills key
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.search_by_metadata(skills=["python"], owner_id=owner_id)

    assert no_skills_doc.id not in {h.id for h in hits}


# ---------------------------------------------------------------------------
# Experience years — cast-safety guard
# ---------------------------------------------------------------------------


async def test_numeric_experience_years_matches_above_threshold(
    owner_id,
) -> None:
    """Happy path — numeric value above threshold is returned."""
    senior = await _seed_doc(
        owner_id=owner_id,
        filename="senior.pdf",
        metadata={"experience_years": 7},
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.search_by_metadata(min_experience_years=5, owner_id=owner_id)

    assert senior.id in {h.id for h in hits}


async def test_numeric_experience_years_below_threshold_excluded(
    owner_id,
) -> None:
    junior = await _seed_doc(
        owner_id=owner_id,
        filename="junior.pdf",
        metadata={"experience_years": 2},
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.search_by_metadata(min_experience_years=5, owner_id=owner_id)

    assert junior.id not in {h.id for h in hits}


async def test_missing_experience_years_excluded_without_crash(
    owner_id,
) -> None:
    """Doc without the key returns NULL typeof → filter evaluates to
    UNKNOWN → row excluded. No 500."""
    no_years = await _seed_doc(
        owner_id=owner_id,
        filename="no_years.pdf",
        metadata={"skills": ["python"]},  # no experience_years
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        # Must not raise
        hits = await repo.search_by_metadata(min_experience_years=5, owner_id=owner_id)

    assert no_years.id not in {h.id for h in hits}


async def test_string_experience_years_excluded_without_crash(
    owner_id,
) -> None:
    """The crash-safety test. A hand-edited or future-classifier-
    regression value like ``"5+"`` must not 500 the query —
    ``jsonb_typeof = 'number'`` guard filters it out."""
    malformed = await _seed_doc(
        owner_id=owner_id,
        filename="malformed.pdf",
        metadata={"experience_years": "5+"},  # string, not number
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        # Must not raise
        hits = await repo.search_by_metadata(min_experience_years=3, owner_id=owner_id)

    assert malformed.id not in {h.id for h in hits}


async def test_list_experience_years_excluded_without_crash(owner_id) -> None:
    """Another malformed shape — a list value. Guard protects us."""
    malformed = await _seed_doc(
        owner_id=owner_id,
        filename="weird_meta.pdf",
        metadata={"experience_years": [3, 5]},
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.search_by_metadata(min_experience_years=3, owner_id=owner_id)

    assert malformed.id not in {h.id for h in hits}


async def test_numeric_and_skill_filter_combined(owner_id) -> None:
    """Integration: both filters at once produce the intersection."""
    target = await _seed_doc(
        owner_id=owner_id,
        filename="ideal.pdf",
        metadata={"skills": ["python", "aws"], "experience_years": 8},
    )
    has_python_but_junior = await _seed_doc(
        owner_id=owner_id,
        filename="junior_python.pdf",
        metadata={"skills": ["python"], "experience_years": 1},
    )
    senior_but_no_python = await _seed_doc(
        owner_id=owner_id,
        filename="senior_java.pdf",
        metadata={"skills": ["java"], "experience_years": 10},
    )

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        hits = await repo.search_by_metadata(
            skills=["python"],
            min_experience_years=5,
            owner_id=owner_id,
        )

    ids = {h.id for h in hits}
    assert target.id in ids
    assert has_python_but_junior.id not in ids
    assert senior_but_no_python.id not in ids
