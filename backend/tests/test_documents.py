"""Document upload behaviour.

Content-hash dedup is the safety net behind the Gmail reconnect fix: even
when connection identity is lost, identical bytes must not become a
second document, a second blob and a second set of vectors.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_identical_bytes_reuse_one_document(admin_user) -> None:
    """The safety net for a Gmail reconnect that re-imports everything."""
    from app.api.deps import _blob_storage
    from app.core.db import SessionLocal
    from app.repositories.document import DocumentRepository
    from app.services.document_service import DocumentService

    data = b"%PDF-1.4 the same resume twice"
    async with SessionLocal() as session:
        svc = DocumentService(
            DocumentRepository(session), _blob_storage, max_file_size_bytes=10_000_000
        )
        first = await svc.upload(
            owner=admin_user,
            filename="resume.pdf",
            mime_type="application/pdf",
            data=data,
        )
        again = await svc.upload(
            owner=admin_user,
            filename="resume-copy.pdf",
            mime_type="application/pdf",
            data=data,
        )
        assert again.id == first.id, "identical bytes must not create a second document"

        different = await svc.upload(
            owner=admin_user,
            filename="other.pdf",
            mime_type="application/pdf",
            data=b"%PDF-1.4 a different file",
        )
        assert different.id != first.id


@pytest.mark.asyncio
async def test_same_bytes_stay_separate_across_owners(admin_user) -> None:
    """Dedup is per owner; one user's file must never resolve to another's."""
    from uuid import uuid4

    from app.api.deps import _blob_storage
    from app.core.db import SessionLocal
    from app.models import User, UserRole
    from app.repositories.document import DocumentRepository
    from app.services.document_service import DocumentService

    data = b"%PDF-1.4 shared bytes"
    async with SessionLocal() as session:
        other = User(
            email=f"other-{uuid4()}@example.com",
            hashed_password="$argon2id$v=19$not-a-real-hash",
            role=UserRole.HR,
            is_active=True,
        )
        session.add(other)
        await session.commit()
        await session.refresh(other)

        svc = DocumentService(
            DocumentRepository(session), _blob_storage, max_file_size_bytes=10_000_000
        )
        mine = await svc.upload(
            owner=admin_user,
            filename="a.pdf",
            mime_type="application/pdf",
            data=data,
        )
        theirs = await svc.upload(
            owner=other,
            filename="a.pdf",
            mime_type="application/pdf",
            data=data,
        )
        assert mine.id != theirs.id
        assert mine.content_sha256 == theirs.content_sha256
