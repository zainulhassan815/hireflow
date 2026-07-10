"""Job status lifecycle: PATCH /api/jobs/{id}/status.

Exercises the transition rules, the no-op case, owner/admin authorization,
and the regression that the generic job update can no longer change status
(the unvalidated bypass this endpoint replaces). Real Postgres via the
``client`` fixture — no service mocks.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.argon2_hasher import Argon2Hasher
from app.core.db import SessionLocal
from app.models import Job, JobStatus, UserRole
from app.repositories.user import UserRepository

pytestmark = pytest.mark.asyncio


async def _create_job(client, token, auth_headers, title: str = "Job") -> dict:
    response = await client.post(
        "/api/jobs",
        json={
            "title": title,
            "description": "Short description for the test job.",
            "required_skills": ["python"],
            "experience_min": 0,
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _seed_job(*, owner_id: UUID, status: JobStatus, title: str = "Seeded") -> Job:
    """Insert a job directly at a given status so transitions from open /
    closed / archived can be tested without walking the lifecycle."""
    async with SessionLocal() as session:
        job = Job(
            owner_id=owner_id,
            title=title,
            description="Seeded job for status tests.",
            required_skills=["python"],
            experience_min=0,
            status=status,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


async def _second_hr_token(client) -> str:
    async with SessionLocal() as session:
        existing = await UserRepository(session).get_by_email("hr-b@test.hireflow.io")
        if existing is None:
            await UserRepository(session).create(
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


async def _status_in_db(job_id: UUID) -> JobStatus:
    async with SessionLocal() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        return job.status


# ---------- auth + existence ----------


async def test_change_status_unauthenticated(client) -> None:
    response = await client.patch(
        f"/api/jobs/{uuid4()}/status", json={"status": "open"}
    )
    assert response.status_code == 401


async def test_change_status_missing_job_404(client, hr_token, auth_headers) -> None:
    response = await client.patch(
        f"/api/jobs/{uuid4()}/status",
        json={"status": "open"},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 404


# ---------- valid transitions ----------


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (JobStatus.DRAFT, JobStatus.OPEN),
        (JobStatus.OPEN, JobStatus.CLOSED),
        (JobStatus.CLOSED, JobStatus.OPEN),
        (JobStatus.CLOSED, JobStatus.ARCHIVED),
        (JobStatus.OPEN, JobStatus.ARCHIVED),
        (JobStatus.DRAFT, JobStatus.ARCHIVED),
    ],
)
async def test_valid_transition(
    client, hr_token, hr_user, auth_headers, from_status, to_status
) -> None:
    job = await _seed_job(owner_id=hr_user.id, status=from_status)

    response = await client.patch(
        f"/api/jobs/{job.id}/status",
        json={"status": to_status.value},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == to_status.value
    assert await _status_in_db(job.id) is to_status


# ---------- illegal transitions ----------


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (JobStatus.ARCHIVED, JobStatus.OPEN),
        (JobStatus.ARCHIVED, JobStatus.CLOSED),
        (JobStatus.OPEN, JobStatus.DRAFT),
        (JobStatus.CLOSED, JobStatus.DRAFT),
    ],
)
async def test_illegal_transition_409(
    client, hr_token, hr_user, auth_headers, from_status, to_status
) -> None:
    job = await _seed_job(owner_id=hr_user.id, status=from_status)

    response = await client.patch(
        f"/api/jobs/{job.id}/status",
        json={"status": to_status.value},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "invalid_status_transition"
    # DB unchanged.
    assert await _status_in_db(job.id) is from_status


async def test_same_status_is_noop_200(client, hr_token, hr_user, auth_headers) -> None:
    job = await _seed_job(owner_id=hr_user.id, status=JobStatus.OPEN)

    response = await client.patch(
        f"/api/jobs/{job.id}/status",
        json={"status": "open"},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "open"
    assert await _status_in_db(job.id) is JobStatus.OPEN


async def test_invalid_status_value_422(
    client, hr_token, hr_user, auth_headers
) -> None:
    job = await _seed_job(owner_id=hr_user.id, status=JobStatus.DRAFT)

    response = await client.patch(
        f"/api/jobs/{job.id}/status",
        json={"status": "bogus"},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 422


# ---------- authorization ----------


async def test_other_hr_cannot_change_status(
    client, hr_token, hr_user, auth_headers
) -> None:
    job = await _seed_job(owner_id=hr_user.id, status=JobStatus.DRAFT)
    token_b = await _second_hr_token(client)

    response = await client.patch(
        f"/api/jobs/{job.id}/status",
        json={"status": "open"},
        headers=auth_headers(token_b),
    )
    assert response.status_code == 403
    assert await _status_in_db(job.id) is JobStatus.DRAFT


async def test_admin_can_change_any_status(
    client, hr_user, admin_token, auth_headers
) -> None:
    job = await _seed_job(owner_id=hr_user.id, status=JobStatus.DRAFT)

    response = await client.patch(
        f"/api/jobs/{job.id}/status",
        json={"status": "open"},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    assert await _status_in_db(job.id) is JobStatus.OPEN


# ---------- regression: generic update no longer changes status ----------


async def test_generic_update_ignores_status(client, hr_token, auth_headers) -> None:
    """`status` was removed from UpdateJobRequest; a stray value in the
    generic PATCH body is dropped (Pydantic extra='ignore'), not applied."""
    job = await _create_job(client, hr_token, auth_headers, "Bypass check")
    assert job["status"] == "draft"

    response = await client.patch(
        f"/api/jobs/{job['id']}",
        json={"title": "Renamed", "status": "open"},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Renamed"
    assert body["status"] == "draft"
    assert await _status_in_db(UUID(job["id"])) is JobStatus.DRAFT
