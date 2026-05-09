"""F32 — GET /api/documents query-param filters.

Backend already had ``DocumentRepository.search_by_metadata`` for the
search path; F32 routes the documents-list endpoint through it when
≥1 filter is set, with ``status=None`` so HR users see pending /
processing / failed rows alongside ready ones.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.db import SessionLocal
from app.models import Document, DocumentStatus, DocumentType


async def _seed_doc(
    *,
    owner_id: UUID,
    filename: str,
    document_type: DocumentType | None = DocumentType.RESUME,
    status: DocumentStatus = DocumentStatus.READY,
    metadata: dict | None = None,
    created_at: datetime | None = None,
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
            metadata_=metadata,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        if created_at is not None:
            # Override the server-default so date-range tests are
            # deterministic. The model's ``created_at`` is a Mapped
            # column — direct assignment + commit lands.
            doc.created_at = created_at
            session.add(doc)
            await session.commit()
            await session.refresh(doc)
        return doc


# ---------- backwards compat ----------


async def test_no_filters_returns_owner_docs_unchanged(
    client, hr_user, hr_token, auth_headers
) -> None:
    """No filters → same shape as before F32 (calls ``list_by_owner``)."""
    await _seed_doc(owner_id=hr_user.id, filename="a.pdf")
    await _seed_doc(owner_id=hr_user.id, filename="b.pdf")

    response = await client.get("/api/documents", headers=auth_headers(hr_token))
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2


# ---------- per-filter ----------


async def test_filter_by_document_type(client, hr_user, hr_token, auth_headers) -> None:
    await _seed_doc(
        owner_id=hr_user.id, filename="r.pdf", document_type=DocumentType.RESUME
    )
    await _seed_doc(
        owner_id=hr_user.id, filename="rep.pdf", document_type=DocumentType.REPORT
    )

    response = await client.get(
        "/api/documents?document_type=resume",
        headers=auth_headers(hr_token),
    )
    body = response.json()
    assert len(body) == 1
    assert body[0]["filename"] == "r.pdf"
    assert body[0]["document_type"] == "resume"


async def test_filter_by_skills_intersection(
    client, hr_user, hr_token, auth_headers
) -> None:
    """Multi-skill filter is intersection (``@>`` on JSONB)."""
    await _seed_doc(
        owner_id=hr_user.id,
        filename="py_react.pdf",
        metadata={"skills": ["python", "react"]},
    )
    await _seed_doc(
        owner_id=hr_user.id,
        filename="py_only.pdf",
        metadata={"skills": ["python"]},
    )
    await _seed_doc(
        owner_id=hr_user.id,
        filename="react_only.pdf",
        metadata={"skills": ["react"]},
    )

    # Single skill → matches both py_react.pdf and py_only.pdf.
    response = await client.get(
        "/api/documents?skills=python",
        headers=auth_headers(hr_token),
    )
    filenames = sorted(d["filename"] for d in response.json())
    assert filenames == ["py_only.pdf", "py_react.pdf"]

    # Two skills → intersection.
    response = await client.get(
        "/api/documents?skills=python&skills=react",
        headers=auth_headers(hr_token),
    )
    filenames = sorted(d["filename"] for d in response.json())
    assert filenames == ["py_react.pdf"]


async def test_filter_by_skills_case_insensitive(
    client, hr_user, hr_token, auth_headers
) -> None:
    await _seed_doc(
        owner_id=hr_user.id,
        filename="cv.pdf",
        metadata={"skills": ["python"]},
    )

    response = await client.get(
        "/api/documents?skills=PYTHON",
        headers=auth_headers(hr_token),
    )
    filenames = [d["filename"] for d in response.json()]
    assert filenames == ["cv.pdf"]


async def test_filter_by_min_experience_years(
    client, hr_user, hr_token, auth_headers
) -> None:
    await _seed_doc(
        owner_id=hr_user.id,
        filename="senior.pdf",
        metadata={"experience_years": 8},
    )
    await _seed_doc(
        owner_id=hr_user.id,
        filename="mid.pdf",
        metadata={"experience_years": 4},
    )
    await _seed_doc(
        owner_id=hr_user.id,
        filename="junior.pdf",
        metadata={"experience_years": 1},
    )

    response = await client.get(
        "/api/documents?min_experience_years=5",
        headers=auth_headers(hr_token),
    )
    filenames = [d["filename"] for d in response.json()]
    assert filenames == ["senior.pdf"]


async def test_filter_by_date_range(client, hr_user, hr_token, auth_headers) -> None:
    now = datetime.now(UTC)
    old = now - timedelta(days=30)
    new = now - timedelta(days=1)

    await _seed_doc(owner_id=hr_user.id, filename="old.pdf", created_at=old)
    await _seed_doc(owner_id=hr_user.id, filename="new.pdf", created_at=new)

    cutoff = (now - timedelta(days=7)).isoformat()
    response = await client.get(
        "/api/documents",
        params={"date_from": cutoff},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200, response.text
    filenames = [d["filename"] for d in response.json()]
    assert filenames == ["new.pdf"]


# ---------- owner scoping ----------


async def test_filter_owner_scoped(
    client, hr_user, hr_token, auth_headers, admin_user
) -> None:
    """Filters apply within the caller's pool only — cross-tenant
    docs never surface even when they match."""
    await _seed_doc(
        owner_id=hr_user.id,
        filename="hr_python.pdf",
        metadata={"skills": ["python"]},
    )
    await _seed_doc(
        owner_id=admin_user.id,
        filename="admin_python.pdf",
        metadata={"skills": ["python"]},
    )

    response = await client.get(
        "/api/documents?skills=python",
        headers=auth_headers(hr_token),
    )
    filenames = [d["filename"] for d in response.json()]
    assert filenames == ["hr_python.pdf"]


# ---------- empty result combo ----------


async def test_filter_combo_with_zero_matches(
    client, hr_user, hr_token, auth_headers
) -> None:
    """A filter combo that matches no docs returns ``200 [] `` —
    not 404, not 500."""
    await _seed_doc(
        owner_id=hr_user.id,
        filename="cv.pdf",
        metadata={"skills": ["python"]},
    )

    response = await client.get(
        "/api/documents?skills=qwerty",
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200
    assert response.json() == []


# ---------- non-ready docs surface under a filter ----------


async def test_filter_includes_non_ready_states(
    client, hr_user, hr_token, auth_headers
) -> None:
    """Plan §1 — when a filter is set, the documents-list path
    still surfaces pending/processing/failed rows so the operator
    sees the full pipeline state."""
    await _seed_doc(
        owner_id=hr_user.id,
        filename="ready.pdf",
        document_type=DocumentType.RESUME,
        status=DocumentStatus.READY,
    )
    await _seed_doc(
        owner_id=hr_user.id,
        filename="processing.pdf",
        document_type=DocumentType.RESUME,
        status=DocumentStatus.PROCESSING,
    )

    response = await client.get(
        "/api/documents?document_type=resume",
        headers=auth_headers(hr_token),
    )
    filenames = sorted(d["filename"] for d in response.json())
    assert filenames == ["processing.pdf", "ready.pdf"]
