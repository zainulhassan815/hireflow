"""F89.c — SearchService.find_similar_documents tests.

The Chroma-specific serialization layer has its own eval coverage.
These tests use an in-memory fake ``DocumentSimilarityStore`` so we
can verify the service's logic independently: ownership scoping,
source-exclusion, NotFound/Forbidden/ServiceUnavailable branches,
READY-filter, and the belt-and-braces post-hydrate owner check.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.adapters.protocols import SimilarDocumentHit
from app.core.db import SessionLocal
from app.domain.exceptions import (
    DocumentNotIndexed,
    Forbidden,
    NotFound,
    ServiceUnavailable,
)
from app.models import Document, DocumentStatus, DocumentType, UserRole
from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository
from app.services.search_service import SearchService


class _FakeSimilarityStore:
    """Minimal in-memory ``DocumentSimilarityStore`` for unit tests.

    Stores per-document hit lists keyed by source. Honours the
    ``where={"owner_id": ...}`` filter so the scoping path can be
    exercised. Raises ``DocumentNotIndexed`` when the source id isn't
    registered — same behaviour as ``ChromaVectorStore``.
    """

    def __init__(self) -> None:
        self._hits: dict[str, list[SimilarDocumentHit]] = {}

    def set_hits(self, source_id: UUID, hits: list[SimilarDocumentHit]) -> None:
        self._hits[str(source_id)] = hits

    def upsert_document_vector(
        self, document_id: str, embedding: list[float], metadata: dict[str, Any]
    ) -> None:
        self._hits.setdefault(document_id, [])

    def delete_document_vector(self, document_id: str) -> None:
        self._hits.pop(document_id, None)

    def find_similar_documents(
        self,
        source_document_id: str,
        n_results: int,
        where: dict[str, Any] | None = None,
    ) -> list[SimilarDocumentHit]:
        if source_document_id not in self._hits:
            raise DocumentNotIndexed("not indexed in fake store")
        hits = self._hits[source_document_id]
        if where and "owner_id" in where:
            owner = where["owner_id"]
            hits = [h for h in hits if h.metadata.get("owner_id") == owner]
        return hits[:n_results]


async def _seed_user(*, role: UserRole, email_slug: str):
    from app.adapters.argon2_hasher import Argon2Hasher

    async with SessionLocal() as session:
        repo = UserRepository(session)
        return await repo.create(
            email=f"{email_slug}-{uuid4()}@test.hireflow.io",
            hashed_password=Argon2Hasher().hash("x"),
            full_name=f"Fixture {email_slug}",
            role=role,
        )


async def _seed_doc(
    *,
    owner_id: UUID,
    filename: str,
    status: DocumentStatus = DocumentStatus.READY,
    document_type: DocumentType | None = DocumentType.RESUME,
) -> Document:
    async with SessionLocal() as session:
        doc = Document(
            owner_id=owner_id,
            filename=filename,
            mime_type="application/pdf",
            size_bytes=100,
            storage_key=f"test/{filename}-{uuid4()}",
            status=status,
            document_type=document_type,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc


def _hit(doc: Document, *, distance: float) -> SimilarDocumentHit:
    return SimilarDocumentHit(
        document_id=str(doc.id),
        distance=distance,
        metadata={
            "document_id": str(doc.id),
            "owner_id": str(doc.owner_id),
        },
    )


@asynccontextmanager
async def _service(*, similarity_store: Any | None) -> AsyncIterator[SearchService]:
    """Yield a ``SearchService`` over a live session.

    The session must outlive every call into the service, so the helper
    is a context manager rather than a plain factory — caller uses
    ``async with _service(...) as svc: ...`` to keep the repository
    alive for the duration of the assertions.
    """
    async with SessionLocal() as session:
        yield SearchService(
            DocumentRepository(session),
            vector_store=None,
            similarity_store=similarity_store,
        )


# ---------------------------------------------------------------------------
# Availability branches
# ---------------------------------------------------------------------------


async def test_service_unavailable_when_store_missing() -> None:
    """No similarity store wired → 503 rather than a silent empty list."""
    owner = await _seed_user(role=UserRole.HR, email_slug="no-store")
    source = await _seed_doc(owner_id=owner.id, filename="source.pdf")

    async with _service(similarity_store=None) as svc:
        with pytest.raises(ServiceUnavailable):
            await svc.find_similar_documents(
                actor=owner, source_document_id=source.id, limit=5
            )


async def test_not_found_when_source_missing() -> None:
    owner = await _seed_user(role=UserRole.HR, email_slug="missing-src")
    store = _FakeSimilarityStore()

    async with _service(similarity_store=store) as svc:
        with pytest.raises(NotFound):
            await svc.find_similar_documents(
                actor=owner, source_document_id=uuid4(), limit=5
            )


async def test_not_found_when_source_is_not_ready() -> None:
    """Processing / failed docs aren't searchable — don't leak status."""
    owner = await _seed_user(role=UserRole.HR, email_slug="pending-src")
    source = await _seed_doc(
        owner_id=owner.id,
        filename="pending.pdf",
        status=DocumentStatus.PROCESSING,
    )
    store = _FakeSimilarityStore()
    store.upsert_document_vector(str(source.id), [0.1] * 3, {})

    async with _service(similarity_store=store) as svc:
        with pytest.raises(NotFound):
            await svc.find_similar_documents(
                actor=owner, source_document_id=source.id, limit=5
            )


async def test_forbidden_when_other_users_source() -> None:
    """HR cannot query similars for another user's document."""
    owner = await _seed_user(role=UserRole.HR, email_slug="real-owner")
    intruder = await _seed_user(role=UserRole.HR, email_slug="intruder")
    source = await _seed_doc(owner_id=owner.id, filename="private.pdf")
    store = _FakeSimilarityStore()
    store.upsert_document_vector(str(source.id), [0.1] * 3, {})

    async with _service(similarity_store=store) as svc:
        with pytest.raises(Forbidden):
            await svc.find_similar_documents(
                actor=intruder, source_document_id=source.id, limit=5
            )


async def test_document_not_indexed_propagates() -> None:
    owner = await _seed_user(role=UserRole.HR, email_slug="unindexed")
    source = await _seed_doc(owner_id=owner.id, filename="never_indexed.pdf")
    store = _FakeSimilarityStore()  # deliberately don't register the source

    async with _service(similarity_store=store) as svc:
        with pytest.raises(DocumentNotIndexed):
            await svc.find_similar_documents(
                actor=owner, source_document_id=source.id, limit=5
            )


# ---------------------------------------------------------------------------
# Ownership scoping
# ---------------------------------------------------------------------------


async def test_hr_sees_only_own_docs_in_results() -> None:
    """Fake store's ``where`` filter scopes by owner_id; service must
    therefore surface only the HR user's own docs in the result."""
    owner = await _seed_user(role=UserRole.HR, email_slug="hr-scope")
    other = await _seed_user(role=UserRole.HR, email_slug="hr-other")
    source = await _seed_doc(owner_id=owner.id, filename="s.pdf")
    mine = await _seed_doc(owner_id=owner.id, filename="mine.pdf")
    theirs = await _seed_doc(owner_id=other.id, filename="theirs.pdf")

    store = _FakeSimilarityStore()
    store.set_hits(source.id, [_hit(mine, distance=0.2), _hit(theirs, distance=0.3)])

    async with _service(similarity_store=store) as svc:
        results = await svc.find_similar_documents(
            actor=owner, source_document_id=source.id, limit=10
        )

    ids = {r.document_id for r in results}
    assert mine.id in ids
    assert theirs.id not in ids


async def test_admin_sees_across_owners() -> None:
    owner = await _seed_user(role=UserRole.HR, email_slug="admin-scope-hr")
    admin = await _seed_user(role=UserRole.ADMIN, email_slug="admin-scope-adm")
    source = await _seed_doc(owner_id=owner.id, filename="s.pdf")
    a = await _seed_doc(owner_id=owner.id, filename="a.pdf")
    b = await _seed_doc(owner_id=admin.id, filename="b.pdf")

    store = _FakeSimilarityStore()
    store.set_hits(source.id, [_hit(a, distance=0.1), _hit(b, distance=0.2)])

    async with _service(similarity_store=store) as svc:
        results = await svc.find_similar_documents(
            actor=admin, source_document_id=source.id, limit=10
        )

    ids = {r.document_id for r in results}
    assert {a.id, b.id} <= ids


async def test_post_hydrate_owner_filter_catches_stale_metadata() -> None:
    """Simulate a stale Chroma metadata row (doc reassigned to another
    owner in Postgres but the Chroma metadata still says the original
    owner). The fake store's ``where`` clause lets the hit through as
    if it matched; the service's post-hydrate filter must drop it."""
    owner = await _seed_user(role=UserRole.HR, email_slug="hydrate-owner")
    other = await _seed_user(role=UserRole.HR, email_slug="hydrate-other")
    source = await _seed_doc(owner_id=owner.id, filename="s.pdf")
    reassigned = await _seed_doc(owner_id=other.id, filename="reassigned.pdf")

    store = _FakeSimilarityStore()
    store.set_hits(
        source.id,
        [
            SimilarDocumentHit(
                document_id=str(reassigned.id),
                distance=0.1,
                metadata={
                    "document_id": str(reassigned.id),
                    "owner_id": str(owner.id),  # stale!
                },
            )
        ],
    )

    async with _service(similarity_store=store) as svc:
        results = await svc.find_similar_documents(
            actor=owner, source_document_id=source.id, limit=10
        )

    assert not results, (
        "stale Chroma metadata leaked a cross-owner doc — post-hydrate "
        "owner filter didn't fire"
    )


# ---------------------------------------------------------------------------
# Exclusion + hydration
# ---------------------------------------------------------------------------


async def test_source_doc_excluded_even_if_returned() -> None:
    """Chroma often ranks the source as its own nearest neighbour.
    The service must drop it before truncation so the user sees
    ``limit`` *other* docs, not ``limit-1`` plus the source."""
    owner = await _seed_user(role=UserRole.HR, email_slug="exclude-src")
    source = await _seed_doc(owner_id=owner.id, filename="source.pdf")
    neighbour = await _seed_doc(owner_id=owner.id, filename="neighbour.pdf")

    store = _FakeSimilarityStore()
    store.set_hits(
        source.id,
        [_hit(source, distance=0.0), _hit(neighbour, distance=0.1)],
    )

    async with _service(similarity_store=store) as svc:
        results = await svc.find_similar_documents(
            actor=owner, source_document_id=source.id, limit=5
        )

    assert [r.document_id for r in results] == [neighbour.id]


async def test_non_ready_neighbours_filtered() -> None:
    owner = await _seed_user(role=UserRole.HR, email_slug="not-ready")
    source = await _seed_doc(owner_id=owner.id, filename="source.pdf")
    stale = await _seed_doc(
        owner_id=owner.id,
        filename="stale.pdf",
        status=DocumentStatus.PROCESSING,
    )
    live = await _seed_doc(owner_id=owner.id, filename="live.pdf")

    store = _FakeSimilarityStore()
    store.set_hits(
        source.id,
        [_hit(stale, distance=0.05), _hit(live, distance=0.1)],
    )

    async with _service(similarity_store=store) as svc:
        results = await svc.find_similar_documents(
            actor=owner, source_document_id=source.id, limit=5
        )

    assert [r.document_id for r in results] == [live.id]


async def test_similarity_score_is_one_minus_distance() -> None:
    """UX exposes cosine *similarity* (higher = better). Distance→
    similarity mapping must be 1 - distance, clipped to 0 for safety
    when distance is numerically >1 (can happen with normalized
    vectors + fp rounding)."""
    owner = await _seed_user(role=UserRole.HR, email_slug="score")
    source = await _seed_doc(owner_id=owner.id, filename="source.pdf")
    close = await _seed_doc(owner_id=owner.id, filename="close.pdf")
    far = await _seed_doc(owner_id=owner.id, filename="far.pdf")
    weird = await _seed_doc(owner_id=owner.id, filename="weird.pdf")

    store = _FakeSimilarityStore()
    store.set_hits(
        source.id,
        [
            _hit(close, distance=0.1),
            _hit(far, distance=0.9),
            _hit(weird, distance=1.2),  # edge of fp; similarity must clip to 0
        ],
    )

    async with _service(similarity_store=store) as svc:
        results = await svc.find_similar_documents(
            actor=owner, source_document_id=source.id, limit=5
        )

    by_id = {r.document_id: r for r in results}
    assert by_id[close.id].similarity == pytest.approx(0.9, abs=1e-9)
    assert by_id[far.id].similarity == pytest.approx(0.1, abs=1e-9)
    assert by_id[weird.id].similarity == pytest.approx(0.0, abs=1e-9)


async def test_limit_truncates_after_exclusion() -> None:
    owner = await _seed_user(role=UserRole.HR, email_slug="limit-trunc")
    source = await _seed_doc(owner_id=owner.id, filename="source.pdf")
    neighbours = [
        await _seed_doc(owner_id=owner.id, filename=f"n{i}.pdf") for i in range(5)
    ]

    store = _FakeSimilarityStore()
    store.set_hits(
        source.id,
        [_hit(source, distance=0.0)]
        + [_hit(n, distance=0.1 * (i + 1)) for i, n in enumerate(neighbours)],
    )

    async with _service(similarity_store=store) as svc:
        results = await svc.find_similar_documents(
            actor=owner, source_document_id=source.id, limit=2
        )

    assert len(results) == 2
    assert [r.document_id for r in results] == [neighbours[0].id, neighbours[1].id]
