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

import re
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from tests.eval.dataset import FIXTURE_DOCS, FixtureDoc

if TYPE_CHECKING:
    from app.adapters.protocols import Element


_ALL_CAPS_HEADING = re.compile(r"^[A-Z][A-Z\s&/+\-]{2,}$")


def _synthesize_elements(text: str) -> list[Element]:
    """Turn a fixture's plain text into typed ``Element`` objects.

    The fixtures are plain strings, not real PDFs — running
    ``unstructured`` on them is slow and pointless. Simulate what a
    layout-aware extractor would produce: split on paragraph breaks,
    detect ALL-CAPS-only lines as Title elements, everything else as
    NarrativeText. Gives the chunker realistic input while keeping the
    eval fast and deterministic.
    """
    from app.adapters.protocols import Element

    elements: list[Element] = []
    order = 0
    for block in re.split(r"\n{2,}", text):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        first = lines[0].strip()
        if _ALL_CAPS_HEADING.match(first):
            elements.append(
                Element(
                    kind="Title",
                    text=first,
                    page_number=1,
                    order=order,
                    metadata={},
                )
            )
            order += 1
            rest = "\n".join(lines[1:]).strip()
            if rest:
                elements.append(
                    Element(
                        kind="NarrativeText",
                        text=rest,
                        page_number=1,
                        order=order,
                        metadata={},
                    )
                )
                order += 1
        else:
            elements.append(
                Element(
                    kind="NarrativeText",
                    text=block,
                    page_number=1,
                    order=order,
                    metadata={},
                )
            )
            order += 1
    return elements


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

        # Also wipe the eval's ChromaDB collections.
        #
        # This used to call ``store.delete(fixture.slug)``, but that
        # method takes a *document id* and the fixtures are seeded under
        # fresh UUIDs — so it deleted nothing, ever. Every run's corpus
        # accumulated instead, in a collection shared with dev data,
        # and matching scores drifted with the junk. Twenty runs' worth
        # (164 vectors across 20 dead owners) had piled up.
        #
        # Dropping the collections outright is both simpler and actually
        # correct. Guarded by the ``_test`` suffix so this can never
        # touch the dev collections.
        try:
            import chromadb

            from app.core.config import settings

            assert settings.chroma_collection_suffix.endswith("_test"), (
                "refusing to drop collections without a _test suffix; "
                f"got {settings.chroma_collection_suffix!r}"
            )
            client = chromadb.HttpClient(
                host=settings.chroma_host, port=settings.chroma_port
            )
            for existing in client.list_collections():
                name = existing if isinstance(existing, str) else existing.name
                if name.endswith(settings.chroma_collection_suffix):
                    client.delete_collection(name)
        except AssertionError:
            raise
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
async def matching_owner(eval_owner):
    """A second owner, holding the matching corpus only.

    The matching résumés live in the same ChromaDB chunk collection as
    the search fixtures, so seeding them under ``eval_owner`` put them
    in front of every search-quality query: running the whole eval
    directory scored p@5 0.2087 where the search eval alone scored
    0.2522, and whichever ran last wrote ``baseline.json``. Ownership
    scoping already isolates them for free — the search actor simply
    never sees another owner's chunks.

    Depends on ``eval_owner`` so it is created after that fixture's
    once-per-session database wipe, not before it.
    """
    from app.adapters.argon2_hasher import Argon2Hasher
    from app.core.db import SessionLocal
    from app.models import UserRole
    from app.repositories.user import UserRepository

    async with SessionLocal() as session:
        return await UserRepository(session).create(
            email="eval-matching-owner@hireflow.test",
            hashed_password=Argon2Hasher().hash("eval-matching-password"),
            full_name="Eval Matching Owner",
            role=UserRole.HR,
        )


@pytest.fixture(scope="session")
async def seeded_fixtures(eval_owner_id: UUID) -> list[tuple[FixtureDoc, UUID]]:
    """Insert every fixture doc into Postgres + ChromaDB.

    Returns ``(fixture, document_id)`` pairs so tests can look up the
    real UUID of a fixture by its slug.
    """
    from app.adapters.chroma_store import ChromaVectorStore
    from app.adapters.contextualizers.registry import get_contextualizer
    from app.adapters.embeddings.registry import get_embedding_provider
    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.models import (
        Document,
        DocumentElement,
        DocumentStatus,
        DocumentType,
    )
    from app.services.chunking import chunk_elements
    from app.services.embedding_service import EmbeddingService

    _assert_test_database(settings.database_url)

    embedder_provider = get_embedding_provider(settings)
    store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        embedder=embedder_provider,
    )
    embedder = EmbeddingService(store, embedder_provider, similarity_store=store)
    contextualizer = get_contextualizer(settings)

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

            # Synthesize typed elements from the fixture plain text so
            # the eval exercises the real F82.e element-aware chunker
            # (we don't actually run unstructured here — that'd be slow
            # and the fixtures are plain strings not PDFs).
            synth_elements = _synthesize_elements(fixture.text)
            for element in synth_elements:
                session.add(
                    DocumentElement(
                        document_id=doc.id,
                        kind=element.kind,
                        text=element.text,
                        page_number=element.page_number,
                        order_index=element.order,
                        metadata_=element.metadata or None,
                    )
                )
            await session.flush()
            # Same pipeline as the real worker: chunk → contextualize → embed.
            # Contextualization respects settings — with
            # CONTEXTUALIZER_PROVIDER=none the path is a passthrough.
            chunks = chunk_elements(synth_elements)
            chunks = contextualizer.contextualize(doc, chunks)
            embedder.index_document(doc, chunks=chunks)

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


# ---------------------------------------------------------------------------
# F45.a — candidate-matching corpus
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
async def seeded_matching_corpus(
    matching_owner,
) -> tuple[dict[str, UUID], dict[str, UUID]]:
    """Seed the matching corpus: candidate résumés (indexed in ChromaDB so
    the vector signal is live), their ``Candidate`` rows, and the jobs.

    Returns ``({candidate_slug: id}, {job_slug: id})``.

    Owned by ``matching_owner``, not ``eval_owner``. Separate slugs are
    not enough to keep this corpus out of the search-quality eval —
    both share one ChromaDB collection, so only ownership scoping
    actually isolates them.
    """
    eval_owner_id = matching_owner.id
    from app.adapters.chroma_store import ChromaVectorStore
    from app.adapters.contextualizers.registry import get_contextualizer
    from app.adapters.embeddings.registry import get_embedding_provider
    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.models import (
        Candidate,
        Document,
        DocumentElement,
        DocumentStatus,
        DocumentType,
        Job,
        JobStatus,
    )
    from app.services.chunking import chunk_elements
    from app.services.embedding_service import EmbeddingService
    from tests.eval.matching_dataset import MATCH_CANDIDATES, MATCH_JOBS

    _assert_test_database(settings.database_url)

    embedder_provider = get_embedding_provider(settings)
    store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        embedder=embedder_provider,
    )
    embedder = EmbeddingService(store, embedder_provider, similarity_store=store)
    contextualizer = get_contextualizer(settings)

    candidate_ids: dict[str, UUID] = {}
    job_ids: dict[str, UUID] = {}

    async with SessionLocal() as session:
        for fixture in MATCH_CANDIDATES:
            doc = Document(
                id=uuid4(),
                owner_id=eval_owner_id,
                filename=fixture.filename,
                mime_type="application/pdf",
                size_bytes=len(fixture.resume_text.encode()),
                storage_key=f"eval-matching/{fixture.slug}",
                status=DocumentStatus.READY,
                document_type=DocumentType.RESUME,
                extracted_text=fixture.resume_text,
                metadata_={"_eval_slug": fixture.slug, "page_count": 1},
            )
            session.add(doc)
            await session.flush()

            elements = _synthesize_elements(fixture.resume_text)
            for element in elements:
                session.add(
                    DocumentElement(
                        document_id=doc.id,
                        kind=element.kind,
                        text=element.text,
                        page_number=element.page_number,
                        order_index=element.order,
                        metadata_=element.metadata or None,
                    )
                )
            await session.flush()

            chunks = chunk_elements(elements)
            chunks = contextualizer.contextualize(doc, chunks)
            embedder.index_document(doc, chunks=chunks)

            candidate = Candidate(
                owner_id=eval_owner_id,
                name=fixture.name,
                skills=list(fixture.skills),
                experience_years=fixture.experience_years,
                source_document_id=doc.id,
            )
            session.add(candidate)
            await session.flush()
            candidate_ids[fixture.slug] = candidate.id

        for job in MATCH_JOBS:
            row = Job(
                owner_id=eval_owner_id,
                title=job.title,
                description=job.description,
                required_skills=list(job.required_skills),
                preferred_skills=list(job.preferred_skills),
                experience_min=job.experience_min,
                experience_max=job.experience_max,
                status=JobStatus.OPEN,
            )
            session.add(row)
            await session.flush()
            job_ids[job.slug] = row.id

        await session.commit()

    assert len(candidate_ids) == len(MATCH_CANDIDATES)
    assert len(job_ids) == len(MATCH_JOBS)
    return candidate_ids, job_ids
