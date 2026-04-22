"""F105.a — GET /documents/{id}/viewable endpoint tests.

Covers the full HTTP path: auth (owner scoping + 404 cross-tenant),
provider dispatch (PDF → ``pdf``, PNG → ``image``, unknown MIME →
``unsupported``), and the not-ready placeholder path. MinIO is the
real localhost service — presigned URLs are generated against it but
we don't require the object to actually exist for a URL-shape
assertion.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.core.db import SessionLocal
from app.models import Document, DocumentStatus, UserRole

pytestmark = pytest.mark.asyncio


async def _seed_doc(
    *,
    owner_id: UUID,
    mime_type: str,
    status: DocumentStatus = DocumentStatus.READY,
    filename: str = "file",
) -> Document:
    async with SessionLocal() as session:
        doc = Document(
            owner_id=owner_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=1024,
            storage_key=f"test/{filename}-{uuid4()}",
            status=status,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return doc


async def test_unauthenticated_rejected(client) -> None:
    response = await client.get(f"/api/documents/{uuid4()}/viewable")
    assert response.status_code == 401


async def test_pdf_returns_pdf_kind_with_signed_url(
    client, hr_user, hr_token, auth_headers
) -> None:
    doc = await _seed_doc(owner_id=hr_user.id, mime_type="application/pdf")

    response = await client.get(
        f"/api/documents/{doc.id}/viewable", headers=auth_headers(hr_token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "pdf"
    # URL-shape assertion (we don't live-HEAD the MinIO URL — MinIO's
    # auth envelope varies and the value here is that the code path
    # produced a signed URL at all).
    assert body["url"] is not None
    assert doc.storage_key in body["url"]
    assert "X-Amz-" in body["url"]
    assert body["data"] is None
    assert body["meta"]["size_bytes"] == 1024


async def test_png_returns_image_kind(client, hr_user, hr_token, auth_headers) -> None:
    doc = await _seed_doc(owner_id=hr_user.id, mime_type="image/png")

    response = await client.get(
        f"/api/documents/{doc.id}/viewable", headers=auth_headers(hr_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "image"
    assert body["url"] is not None
    assert body["meta"]["mime_type"] == "image/png"


async def test_unknown_mime_returns_unsupported(
    client, hr_user, hr_token, auth_headers
) -> None:
    # The upload path would reject ``application/zip``; we seed it
    # directly to exercise the fallback that the registry is there to
    # catch — Gmail-ingested docs or future upload-path changes could
    # land a MIME no provider handles.
    doc = await _seed_doc(
        owner_id=hr_user.id, mime_type="application/zip", filename="archive.zip"
    )

    response = await client.get(
        f"/api/documents/{doc.id}/viewable", headers=auth_headers(hr_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "unsupported"
    assert body["url"] is None
    assert body["meta"]["reason"] == "no_viewer_for_mime"
    assert body["meta"]["filename"] == "archive.zip"


async def test_not_ready_document_returns_unsupported_with_reason(
    client, hr_user, hr_token, auth_headers
) -> None:
    doc = await _seed_doc(
        owner_id=hr_user.id,
        mime_type="application/pdf",
        status=DocumentStatus.PROCESSING,
    )

    response = await client.get(
        f"/api/documents/{doc.id}/viewable", headers=auth_headers(hr_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "unsupported"
    assert body["meta"]["reason"] == "not_ready"
    assert body["meta"]["status"] == "processing"


async def test_missing_document_404(client, hr_token, auth_headers) -> None:
    response = await client.get(
        f"/api/documents/{uuid4()}/viewable", headers=auth_headers(hr_token)
    )
    assert response.status_code == 404


async def test_other_users_document_forbidden(
    client, hr_user, hr_token, auth_headers
) -> None:
    """Non-owner HR users get 403 via ``DocumentService._ensure_access``.

    Same shape as the existing document endpoints — consistency
    matters more than hiding existence here, because sibling
    endpoints already 403.
    """
    from app.adapters.argon2_hasher import Argon2Hasher
    from app.repositories.user import UserRepository

    async with SessionLocal() as session:
        other = await UserRepository(session).create(
            email=f"other-{uuid4()}@example.com",
            hashed_password=Argon2Hasher().hash("other-password"),
            full_name="Other HR",
            role=UserRole.HR,
        )

    doc = await _seed_doc(owner_id=other.id, mime_type="application/pdf")

    response = await client.get(
        f"/api/documents/{doc.id}/viewable", headers=auth_headers(hr_token)
    )
    assert response.status_code == 403


async def test_admin_bypass_sees_any_document(
    client, admin_token, auth_headers, hr_user
) -> None:
    doc = await _seed_doc(owner_id=hr_user.id, mime_type="application/pdf")

    response = await client.get(
        f"/api/documents/{doc.id}/viewable", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    assert response.json()["kind"] == "pdf"
