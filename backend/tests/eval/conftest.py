"""Eval harness conftest — distinct from the unit-test conftest.

Two key overrides:

1. Disable the ``clean_database`` / ``clean_redis`` autouse fixtures
   from ``tests/conftest.py``. Those truncate between every test,
   which would destroy our fixture documents mid-run.
2. Seed the fixture documents (Postgres rows + ChromaDB chunks) once
   per eval session.

Eval also runs with a separate owner user and a separate ChromaDB
collection name so it doesn't collide with dev data if the dev stack
is running.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from uuid import UUID, uuid4

import pytest

from tests.eval.dataset import FIXTURE_DOCS, FixtureDoc

# ---------------------------------------------------------------------------
# Override test-wide autouse fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    """No-op: fixture docs must survive across eval tests."""
    yield


@pytest.fixture(autouse=True)
async def clean_redis() -> AsyncIterator[None]:
    yield


@pytest.fixture(autouse=True)
def enqueued_tasks() -> Iterator[None]:
    """No-op: eval doesn't exercise Celery."""
    yield


# ---------------------------------------------------------------------------
# One-time seed of fixture documents
# ---------------------------------------------------------------------------


def _assert_test_database(database_url: str) -> None:
    """Blow up loudly if the eval is pointed at a non-test database.

    Hand-wired safety net after a previous run wiped the dev DB because
    ``pytest_configure`` hadn't yet swapped env vars at the time the
    ``settings`` module loaded. Runs on *every* entry point that could
    delete rows — belt-and-braces against the same bug recurring.
    """
    if "_test" not in database_url.rsplit("/", 1)[-1]:
        raise RuntimeError(
            f"Eval harness refusing to run: database URL {database_url!r} "
            "does not target a *_test database. Set DATABASE_URL explicitly "
            "or use 'make eval' which handles it."
        )


@pytest.fixture(scope="session")
async def eval_owner():
    """A deterministic owner user seeded for every eval run.

    Returns the full User object so tests can pass it as the search
    ``actor`` (F86 ownership scoping). The companion ``eval_owner_id``
    fixture exposes just the UUID for seeding code that doesn't need
    the full row.
    """
    from sqlalchemy import delete

    from app.adapters.argon2_hasher import Argon2Hasher
    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.models import (
        ActivityLog,
        Application,
        Candidate,
        GmailConnection,
        GmailIngestedMessage,
        UserRole,
    )
    from app.models import Document as DocumentModel
    from app.models import User as UserModel
    from app.repositories.user import UserRepository

    _assert_test_database(settings.database_url)

    async with SessionLocal() as session:
        # Clean out the test DB exactly once at session start so a
        # prior eval run (or a unit-test run) doesn't leave state.
        for model in (
            ActivityLog,
            Application,
            Candidate,
            DocumentModel,
            GmailIngestedMessage,
            GmailConnection,
            UserModel,
        ):
            await session.execute(delete(model))
        await session.commit()

        # Also wipe the ChromaDB documents collection. We don't have a
        # "truncate collection" API; delete-by-filter covers it.
        try:
            from app.adapters.chroma_store import ChromaVectorStore
            from app.core.config import settings

            store = ChromaVectorStore(
                host=settings.chroma_host, port=settings.chroma_port
            )
            # Delete every chunk we'll seed. We know the slugs.
            for fixture in FIXTURE_DOCS:
                store.delete(fixture.slug)
        except Exception:
            # If Chroma is down the eval will fail explicitly below.
            pass

        user = await UserRepository(session).create(
            email="eval-owner@hireflow.test",
            hashed_password=Argon2Hasher().hash("eval-owner-password"),
            full_name="Eval Owner",
            role=UserRole.HR,
        )
        return user


@pytest.fixture(scope="session")
async def eval_owner_id(eval_owner) -> UUID:
    """UUID convenience for seeding code that doesn't need the full User."""
    return eval_owner.id


@pytest.fixture(scope="session")
async def seeded_fixtures(eval_owner_id: UUID) -> list[tuple[FixtureDoc, UUID]]:
    """Insert every fixture doc into Postgres + ChromaDB.

    Returns ``(fixture, document_id)`` pairs so tests can look up the
    real UUID of a fixture by its slug.
    """
    from app.adapters.chroma_store import ChromaVectorStore
    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.models import Document, DocumentStatus, DocumentType
    from app.services.chunking import chunk_text
    from app.services.embedding_service import EmbeddingService

    _assert_test_database(settings.database_url)

    store = ChromaVectorStore(host=settings.chroma_host, port=settings.chroma_port)
    embedder = EmbeddingService(store)

    pairs: list[tuple[FixtureDoc, UUID]] = []
    async with SessionLocal() as session:
        for fixture in FIXTURE_DOCS:
            doc_type = DocumentType(fixture.document_type)
            doc = Document(
                id=uuid4(),
                owner_id=eval_owner_id,
                filename=fixture.filename,
                mime_type="application/pdf",
                size_bytes=len(fixture.text.encode()),
                storage_key=f"eval/{fixture.slug}",
                status=DocumentStatus.READY,
                document_type=doc_type,
                extracted_text=fixture.text,
                metadata_={
                    **fixture.metadata,
                    "page_count": 1,
                    "_eval_slug": fixture.slug,
                },
            )
            session.add(doc)
            await session.flush()

            # Override the chunk indexing to use the fixture's slug as
            # the collection key — makes cleanup deterministic.
            chunks = chunk_text(fixture.text)
            metadatas = [
                {
                    "filename": fixture.filename,
                    "mime_type": "application/pdf",
                    "owner_id": str(eval_owner_id),
                    "document_type": doc_type.value,
                    "document_id": str(doc.id),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                }
                for i in range(len(chunks))
            ]
            store.upsert(str(doc.id), chunks, metadatas)

            pairs.append((fixture, doc.id))

        await session.commit()

    # Sanity: ensure every fixture was indexed.
    assert len(pairs) == len(FIXTURE_DOCS)
    # Unused but keeps the embedder import honest for tooling.
    _ = embedder
    return pairs


@pytest.fixture(scope="session")
def slug_to_document_id(
    seeded_fixtures: list[tuple[FixtureDoc, UUID]],
) -> dict[str, UUID]:
    return {fixture.slug: doc_id for fixture, doc_id in seeded_fixtures}


@pytest.fixture(scope="session")
def document_id_to_slug(
    seeded_fixtures: list[tuple[FixtureDoc, UUID]],
) -> dict[UUID, str]:
    return {doc_id: fixture.slug for fixture, doc_id in seeded_fixtures}
