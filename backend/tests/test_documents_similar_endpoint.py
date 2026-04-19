"""F89.c — POST /documents/{id}/similar endpoint tests.

Exercises the full HTTP path: auth, validation, permission enforcement,
and response envelope shape. A fake ``DocumentSimilarityStore`` is
swapped in via ``monkeypatch`` so the tests don't need a live Chroma
server — the Chroma-specific wire layer is covered by the eval harness.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.adapters.protocols import SimilarDocumentHit
from app.core.db import SessionLocal
from app.domain.exceptions import DocumentNotIndexed
from app.models import Document, DocumentStatus, DocumentType


class _FakeSimilarityStore:
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
            raise DocumentNotIndexed("not indexed")
        hits = self._hits[source_document_id]
        if where and "owner_id" in where:
            owner = where["owner_id"]
            hits = [h for h in hits if h.metadata.get("owner_id") == owner]
        return hits[:n_results]


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


@pytest.fixture
def fake_similarity_store(monkeypatch: pytest.MonkeyPatch) -> _FakeSimilarityStore:
    """Swap the module-level similarity store for a predictable fake.

    The composition root in ``app.api.deps`` caches the Chroma-backed
    store in ``_similarity_store`` at import time; overriding it via
    ``monkeypatch`` means every request for this test sees the fake.
    """
    store = _FakeSimilarityStore()
    monkeypatch.setattr("app.api.deps._similarity_store", store)
    return store


async def test_unauthenticated_rejected(client) -> None:
    response = await client.post(f"/api/documents/{uuid4()}/similar", json={"limit": 5})
    assert response.status_code == 401


async def test_happy_path_returns_neighbours(
    client, hr_user, hr_token, auth_headers, fake_similarity_store
) -> None:
    source = await _seed_doc(owner_id=hr_user.id, filename="source.pdf")
    neighbour = await _seed_doc(owner_id=hr_user.id, filename="neighbour.pdf")
    fake_similarity_store.set_hits(
        source.id,
        [_hit(source, distance=0.0), _hit(neighbour, distance=0.2)],
    )

    response = await client.post(
        f"/api/documents/{source.id}/similar",
        json={"limit": 5},
        headers=auth_headers(hr_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_document_id"] == str(source.id)
    assert len(body["results"]) == 1
    assert body["results"][0]["document_id"] == str(neighbour.id)
    assert body["results"][0]["filename"] == "neighbour.pdf"
    assert body["results"][0]["similarity"] == pytest.approx(0.8, abs=1e-9)


async def test_limit_default_when_body_omitted(
    client, hr_user, hr_token, auth_headers, fake_similarity_store
) -> None:
    """Empty body should use the schema default of 10, not 422."""
    source = await _seed_doc(owner_id=hr_user.id, filename="source.pdf")
    fake_similarity_store.set_hits(source.id, [])

    response = await client.post(
        f"/api/documents/{source.id}/similar",
        json={},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200, response.text


async def test_limit_out_of_range_rejected(
    client, hr_user, hr_token, auth_headers, fake_similarity_store
) -> None:
    source = await _seed_doc(owner_id=hr_user.id, filename="source.pdf")
    fake_similarity_store.set_hits(source.id, [])

    response = await client.post(
        f"/api/documents/{source.id}/similar",
        json={"limit": 0},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 422


async def test_source_not_found(
    client, hr_token, auth_headers, fake_similarity_store
) -> None:
    response = await client.post(
        f"/api/documents/{uuid4()}/similar",
        json={"limit": 5},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_source_not_indexed_returns_404(
    client, hr_user, hr_token, auth_headers, fake_similarity_store
) -> None:
    """Source exists in Postgres but never indexed → distinct 404
    with the ``document_not_indexed`` error code."""
    source = await _seed_doc(owner_id=hr_user.id, filename="source.pdf")
    # Note: deliberately NOT calling ``set_hits`` — fake store raises
    # DocumentNotIndexed on unknown sources.

    response = await client.post(
        f"/api/documents/{source.id}/similar",
        json={"limit": 5},
        headers=auth_headers(hr_token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "document_not_indexed"


async def test_cross_owner_forbidden(
    client, hr_user, hr_token, auth_headers, admin_user, fake_similarity_store
) -> None:
    """HR user can't query similars for another user's document."""
    other_doc = await _seed_doc(owner_id=admin_user.id, filename="admins.pdf")
    fake_similarity_store.set_hits(other_doc.id, [])

    response = await client.post(
        f"/api/documents/{other_doc.id}/similar",
        json={"limit": 5},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 403


async def test_admin_sees_across_owners(
    client,
    hr_user,
    admin_user,
    admin_token,
    auth_headers,
    fake_similarity_store,
) -> None:
    source = await _seed_doc(owner_id=hr_user.id, filename="source.pdf")
    admin_doc = await _seed_doc(owner_id=admin_user.id, filename="admin_doc.pdf")
    fake_similarity_store.set_hits(source.id, [_hit(admin_doc, distance=0.2)])

    response = await client.post(
        f"/api/documents/{source.id}/similar",
        json={"limit": 5},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["results"][0]["document_id"] == str(admin_doc.id)


async def test_service_unavailable_when_not_configured(
    client, hr_user, hr_token, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the deploy lacks Chroma, the similarity store is ``None`` →
    endpoint reports 503 instead of a silent empty list."""
    source = await _seed_doc(owner_id=hr_user.id, filename="source.pdf")
    monkeypatch.setattr("app.api.deps._similarity_store", None)

    response = await client.post(
        f"/api/documents/{source.id}/similar",
        json={"limit": 5},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
