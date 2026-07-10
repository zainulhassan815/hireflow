"""Multi-file candidate submissions (F46): attachment CRUD, ingestion
merge, and the credential_match scoring signal.

Real Postgres via the ``client`` fixture — no service mocks. Documents and
candidates are seeded directly so each behaviour is exercised in isolation.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.argon2_hasher import Argon2Hasher
from app.core.db import SessionLocal
from app.models import (
    Application,
    Candidate,
    CandidateAttachment,
    Document,
    DocumentStatus,
    DocumentType,
    Job,
    JobStatus,
    UserRole,
)
from app.repositories.user import UserRepository

pytestmark = pytest.mark.asyncio


async def _seed_document(
    owner_id: UUID,
    *,
    skills: list[str] | None = None,
    filename: str = "doc.pdf",
    doc_type: DocumentType | None = None,
) -> Document:
    async with SessionLocal() as s:
        doc = Document(
            owner_id=owner_id,
            filename=filename,
            mime_type="application/pdf",
            size_bytes=1024,
            storage_key=f"key/{uuid4()}",
            status=DocumentStatus.READY,
            document_type=doc_type,
            metadata_={"skills": skills} if skills is not None else None,
        )
        s.add(doc)
        await s.commit()
        await s.refresh(doc)
        return doc


async def _seed_candidate(
    owner_id: UUID,
    *,
    skills: list[str] | None = None,
    source_document_id: UUID | None = None,
    experience_years: int | None = 3,
) -> Candidate:
    async with SessionLocal() as s:
        c = Candidate(
            owner_id=owner_id,
            name="Cand",
            email=f"c-{uuid4()}@example.com",
            skills=skills or [],
            experience_years=experience_years,
            source_document_id=source_document_id,
        )
        s.add(c)
        await s.commit()
        await s.refresh(c)
        return c


async def _seed_job(owner_id: UUID, *, required: list[str]) -> Job:
    async with SessionLocal() as s:
        job = Job(
            owner_id=owner_id,
            title="Cloud Engineer",
            description="Own the cloud platform.",
            required_skills=required,
            experience_min=0,
            status=JobStatus.OPEN,
        )
        s.add(job)
        await s.commit()
        await s.refresh(job)
        return job


async def _second_hr_token(client) -> str:
    async with SessionLocal() as s:
        if await UserRepository(s).get_by_email("hr-b@test.hireflow.io") is None:
            await UserRepository(s).create(
                email="hr-b@test.hireflow.io",
                hashed_password=Argon2Hasher().hash("hr-b-password"),
                full_name="HR B",
                role=UserRole.HR,
            )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "hr-b@test.hireflow.io", "password": "hr-b-password"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ---------- attachment CRUD ----------


async def test_attach_unauthenticated(client) -> None:
    resp = await client.post(
        f"/api/candidates/{uuid4()}/attachments",
        json={"attachments": [{"document_id": str(uuid4()), "role": "resume"}]},
    )
    assert resp.status_code == 401


async def test_attach_missing_candidate_404(client, hr_token, hr_user, auth_headers):
    doc = await _seed_document(hr_user.id)
    resp = await client.post(
        f"/api/candidates/{uuid4()}/attachments",
        json={"attachments": [{"document_id": str(doc.id), "role": "resume"}]},
        headers=auth_headers(hr_token),
    )
    assert resp.status_code == 404


async def test_owner_attaches_resume_and_cert(client, hr_token, hr_user, auth_headers):
    candidate = await _seed_candidate(hr_user.id)
    resume = await _seed_document(hr_user.id, filename="resume.pdf")
    cert = await _seed_document(hr_user.id, filename="aws-cert.pdf", skills=["aws"])

    resp = await client.post(
        f"/api/candidates/{candidate.id}/attachments",
        json={
            "attachments": [
                {"document_id": str(resume.id), "role": "resume"},
                {"document_id": str(cert.id), "role": "certificate"},
            ]
        },
        headers=auth_headers(hr_token),
    )
    assert resp.status_code == 201, resp.text
    roles = {a["document_id"]: a["role"] for a in resp.json()}
    assert roles[str(resume.id)] == "resume"
    assert roles[str(cert.id)] == "certificate"

    # Resume attachment repoints source_document_id.
    async with SessionLocal() as s:
        refreshed = await s.get(Candidate, candidate.id)
        assert refreshed.source_document_id == resume.id


async def test_second_resume_409(client, hr_token, hr_user, auth_headers):
    candidate = await _seed_candidate(hr_user.id)
    r1 = await _seed_document(hr_user.id, filename="r1.pdf")
    r2 = await _seed_document(hr_user.id, filename="r2.pdf")
    await client.post(
        f"/api/candidates/{candidate.id}/attachments",
        json={"attachments": [{"document_id": str(r1.id), "role": "resume"}]},
        headers=auth_headers(hr_token),
    )
    resp = await client.post(
        f"/api/candidates/{candidate.id}/attachments",
        json={"attachments": [{"document_id": str(r2.id), "role": "resume"}]},
        headers=auth_headers(hr_token),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "resume_already_attached"


async def test_attach_is_idempotent(client, hr_token, hr_user, auth_headers):
    candidate = await _seed_candidate(hr_user.id)
    cert = await _seed_document(hr_user.id, skills=["aws"])
    body = {"attachments": [{"document_id": str(cert.id), "role": "certificate"}]}
    await client.post(
        f"/api/candidates/{candidate.id}/attachments",
        json=body,
        headers=auth_headers(hr_token),
    )
    # Re-attaching the same document is skipped, not a duplicate / 500.
    resp = await client.post(
        f"/api/candidates/{candidate.id}/attachments",
        json=body,
        headers=auth_headers(hr_token),
    )
    assert resp.status_code == 201
    assert resp.json() == []
    async with SessionLocal() as s:
        rows = await candidate_attachment_count(s, candidate.id)
    assert rows == 1


async def candidate_attachment_count(session, candidate_id: UUID) -> int:
    from sqlalchemy import func, select

    return await session.scalar(
        select(func.count())
        .select_from(CandidateAttachment)
        .where(CandidateAttachment.candidate_id == candidate_id)
    )


async def test_other_hr_cannot_attach(client, hr_token, hr_user, auth_headers):
    candidate = await _seed_candidate(hr_user.id)
    doc = await _seed_document(hr_user.id)
    token_b = await _second_hr_token(client)
    resp = await client.post(
        f"/api/candidates/{candidate.id}/attachments",
        json={"attachments": [{"document_id": str(doc.id), "role": "resume"}]},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 403


async def test_list_and_detach(client, hr_token, hr_user, auth_headers):
    candidate = await _seed_candidate(hr_user.id)
    resume = await _seed_document(hr_user.id, filename="resume.pdf")
    await client.post(
        f"/api/candidates/{candidate.id}/attachments",
        json={"attachments": [{"document_id": str(resume.id), "role": "resume"}]},
        headers=auth_headers(hr_token),
    )
    listed = await client.get(
        f"/api/candidates/{candidate.id}/attachments",
        headers=auth_headers(hr_token),
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    detach = await client.delete(
        f"/api/candidates/{candidate.id}/attachments/{resume.id}",
        headers=auth_headers(hr_token),
    )
    assert detach.status_code == 204

    async with SessionLocal() as s:
        # Attachment gone, but the Document itself stays; resume pointer clears.
        assert await candidate_attachment_count(s, candidate.id) == 0
        assert await s.get(Document, resume.id) is not None
        cand = await s.get(Candidate, candidate.id)
        assert cand.source_document_id is None


# ---------- ingestion merge ----------


async def test_certificate_skills_merge_into_candidate(
    client, hr_token, hr_user, auth_headers
):
    candidate = await _seed_candidate(hr_user.id, skills=["python"])
    cert = await _seed_document(hr_user.id, skills=["kubernetes", "python"])
    await client.post(
        f"/api/candidates/{candidate.id}/attachments",
        json={"attachments": [{"document_id": str(cert.id), "role": "certificate"}]},
        headers=auth_headers(hr_token),
    )
    async with SessionLocal() as s:
        cand = await s.get(Candidate, candidate.id)
        # Union, not append — python isn't duplicated, kubernetes is added.
        assert set(cand.skills) == {"python", "kubernetes"}


# ---------- scoring ----------


async def test_credential_lifts_score(client, hr_token, hr_user, auth_headers):
    job = await _seed_job(hr_user.id, required=["python", "kubernetes"])

    # A: python resume + AWS/k8s certificate covering the missed required skill.
    cand_a = await _seed_candidate(hr_user.id, skills=["python"])
    cert = await _seed_document(hr_user.id, skills=["kubernetes"])
    await client.post(
        f"/api/candidates/{cand_a.id}/attachments",
        json={"attachments": [{"document_id": str(cert.id), "role": "certificate"}]},
        headers=auth_headers(hr_token),
    )
    # B: identical resume, no credentials.
    cand_b = await _seed_candidate(hr_user.id, skills=["python"])

    resp = await client.post(
        f"/api/jobs/{job.id}/match", headers=auth_headers(hr_token)
    )
    assert resp.status_code == 200, resp.text
    by_id = {r["candidate"]["id"]: r for r in resp.json()["results"]}
    a, b = by_id[str(cand_a.id)], by_id[str(cand_b.id)]

    assert a["breakdown"]["credential_match"] == pytest.approx(0.5)  # 1 of 2 targets
    assert b["breakdown"]["credential_match"] == 0.0
    assert a["score"] > b["score"]


async def test_breakdown_persists_credential_match(
    client, hr_token, hr_user, auth_headers
):
    job = await _seed_job(hr_user.id, required=["python"])
    await _seed_candidate(hr_user.id, skills=["python"])
    await client.post(f"/api/jobs/{job.id}/match", headers=auth_headers(hr_token))

    apps = await client.get(
        f"/api/candidates/jobs/{job.id}/applications", headers=auth_headers(hr_token)
    )
    assert apps.status_code == 200
    assert apps.json()[0]["breakdown"]["credential_match"] == 0.0


async def test_legacy_breakdown_without_credential_renders_null(
    client, hr_token, hr_user, auth_headers
):
    """Applications matched before F46 have no credential_match key; the
    response surfaces it as null rather than failing validation."""
    job = await _seed_job(hr_user.id, required=["python"])
    cand = await _seed_candidate(hr_user.id, skills=["python"])
    async with SessionLocal() as s:
        s.add(
            Application(
                candidate_id=cand.id,
                job_id=job.id,
                score=0.5,
                match_breakdown={
                    "skill_match": 1.0,
                    "experience_fit": 1.0,
                    "vector_similarity": 0.0,
                },
            )
        )
        await s.commit()

    apps = await client.get(
        f"/api/candidates/jobs/{job.id}/applications", headers=auth_headers(hr_token)
    )
    assert apps.status_code == 200
    assert apps.json()[0]["breakdown"]["credential_match"] is None
