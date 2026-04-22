"""F44.a — authorization + happy-path tests for application endpoints.

Two endpoints, two auth gaps closed in F44.a:

- ``PATCH /api/candidates/applications/{id}/status``
- ``GET /api/candidates/jobs/{job_id}/applications``

Both must be owner-scoped via ``job.owner_id``; admins bypass. Cross-
tenant attempts return 403 (matches Document/Candidate/Job convention;
403 over 404 is deliberate — consistency beats the marginal
information-hiding win). Missing resources stay 404.

Tests exercise the real DB (Postgres in docker-compose) via the
``client`` fixture — no service mocks — so a future refactor that
breaks authorization surfaces here loudly.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.core.db import SessionLocal
from app.models import (
    Application,
    ApplicationStatus,
    Candidate,
    UserRole,
)

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


async def _seed_candidate_and_application(
    *, owner_id: UUID, job_id: UUID
) -> tuple[Candidate, Application]:
    """Insert a candidate owned by ``owner_id`` and an application linking
    it to ``job_id``. Bypasses the HTTP apply flow so we can test the
    status-change path in isolation."""
    async with SessionLocal() as session:
        candidate = Candidate(
            owner_id=owner_id,
            name="Test Candidate",
            email=f"cand-{uuid4()}@example.com",
            skills=["python"],
        )
        session.add(candidate)
        await session.commit()
        await session.refresh(candidate)

        app = Application(
            candidate_id=candidate.id,
            job_id=job_id,
            status=ApplicationStatus.NEW,
            score=0.75,
        )
        session.add(app)
        await session.commit()
        await session.refresh(app)
        return candidate, app


async def _second_hr_token(client) -> str:
    """Seed a second HR user and return their JWT."""
    from app.adapters.argon2_hasher import Argon2Hasher
    from app.repositories.user import UserRepository

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


# ---------- PATCH status -------------------------------------------------


async def test_update_status_unauthenticated(client) -> None:
    response = await client.patch(
        f"/api/candidates/applications/{uuid4()}/status",
        json={"status": "shortlisted"},
    )
    assert response.status_code == 401


async def test_update_status_missing_application_404(
    client, hr_token, hr_user, auth_headers
) -> None:
    response = await client.patch(
        f"/api/candidates/applications/{uuid4()}/status",
        json={"status": "shortlisted"},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 404


async def test_owner_can_shortlist_own_application(
    client, hr_token, hr_user, auth_headers
) -> None:
    job = await _create_job(client, hr_token, auth_headers, "My job")
    _, app = await _seed_candidate_and_application(
        owner_id=hr_user.id, job_id=UUID(job["id"])
    )

    response = await client.patch(
        f"/api/candidates/applications/{app.id}/status",
        json={"status": "shortlisted"},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "shortlisted"
    assert body["id"] == str(app.id)

    # DB row actually flipped — not just the response envelope.
    async with SessionLocal() as session:
        refreshed = await session.get(Application, app.id)
        assert refreshed is not None
        assert refreshed.status is ApplicationStatus.SHORTLISTED


async def test_other_hr_cannot_update_status(
    client, hr_token, hr_user, auth_headers
) -> None:
    """HR B sees HR A's job exists (403 over 404) and is blocked from
    touching it. The 403-not-404 shape matches JobService /
    DocumentService / CandidateService; consistency beats
    hide-existence here."""
    job = await _create_job(client, hr_token, auth_headers, "HR A's job")
    _, app = await _seed_candidate_and_application(
        owner_id=hr_user.id, job_id=UUID(job["id"])
    )

    token_b = await _second_hr_token(client)

    response = await client.patch(
        f"/api/candidates/applications/{app.id}/status",
        json={"status": "shortlisted"},
        headers=auth_headers(token_b),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"

    # DB row is NOT flipped.
    async with SessionLocal() as session:
        refreshed = await session.get(Application, app.id)
        assert refreshed.status is ApplicationStatus.NEW


async def test_admin_can_update_any_status(
    client, hr_token, hr_user, admin_token, auth_headers
) -> None:
    job = await _create_job(client, hr_token, auth_headers, "HR's job")
    _, app = await _seed_candidate_and_application(
        owner_id=hr_user.id, job_id=UUID(job["id"])
    )

    response = await client.patch(
        f"/api/candidates/applications/{app.id}/status",
        json={"status": "rejected"},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


@pytest.mark.parametrize(
    "target",
    ["shortlisted", "rejected", "interviewed", "hired", "new"],
)
async def test_every_valid_transition(
    client, hr_token, hr_user, auth_headers, target: str
) -> None:
    """Every enum value is reachable from ``new``. F44 UI only exposes
    shortlist/reject, but the endpoint mustn't reject programmatic
    transitions to interviewed/hired — F93 Kanban will drive those."""
    job = await _create_job(client, hr_token, auth_headers, f"Job for {target}")
    _, app = await _seed_candidate_and_application(
        owner_id=hr_user.id, job_id=UUID(job["id"])
    )

    response = await client.patch(
        f"/api/candidates/applications/{app.id}/status",
        json={"status": target},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200
    assert response.json()["status"] == target


# ---------- GET /jobs/{id}/applications ----------------------------------


async def test_list_applications_unauthenticated(client) -> None:
    response = await client.get(f"/api/candidates/jobs/{uuid4()}/applications")
    assert response.status_code == 401


async def test_list_applications_missing_job_404(
    client, hr_token, auth_headers
) -> None:
    response = await client.get(
        f"/api/candidates/jobs/{uuid4()}/applications",
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 404


async def test_owner_sees_own_job_applications(
    client, hr_token, hr_user, auth_headers
) -> None:
    job = await _create_job(client, hr_token, auth_headers, "Owner lists this")
    await _seed_candidate_and_application(owner_id=hr_user.id, job_id=UUID(job["id"]))
    await _seed_candidate_and_application(owner_id=hr_user.id, job_id=UUID(job["id"]))

    response = await client.get(
        f"/api/candidates/jobs/{job['id']}/applications",
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(row["job_id"] == job["id"] for row in body)


async def test_other_hr_cannot_list_applications(
    client, hr_token, hr_user, auth_headers
) -> None:
    job = await _create_job(client, hr_token, auth_headers, "HR A's job")
    await _seed_candidate_and_application(owner_id=hr_user.id, job_id=UUID(job["id"]))

    token_b = await _second_hr_token(client)

    response = await client.get(
        f"/api/candidates/jobs/{job['id']}/applications",
        headers=auth_headers(token_b),
    )
    assert response.status_code == 403


async def test_admin_can_list_any_job_applications(
    client, hr_token, hr_user, admin_token, auth_headers
) -> None:
    job = await _create_job(client, hr_token, auth_headers, "HR job")
    await _seed_candidate_and_application(owner_id=hr_user.id, job_id=UUID(job["id"]))

    response = await client.get(
        f"/api/candidates/jobs/{job['id']}/applications",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_list_applications_status_filter_is_still_honored(
    client, hr_token, hr_user, auth_headers
) -> None:
    """The auth check must not break the pre-existing status filter."""
    job = await _create_job(client, hr_token, auth_headers, "Mixed statuses")

    async with SessionLocal() as session:
        for status in (
            ApplicationStatus.NEW,
            ApplicationStatus.SHORTLISTED,
            ApplicationStatus.SHORTLISTED,
        ):
            candidate = Candidate(
                owner_id=hr_user.id,
                name=f"Cand-{uuid4()}",
                email=f"c-{uuid4()}@x.com",
            )
            session.add(candidate)
            await session.flush()
            session.add(
                Application(
                    candidate_id=candidate.id,
                    job_id=UUID(job["id"]),
                    status=status,
                    score=0.5,
                )
            )
        await session.commit()

    response = await client.get(
        f"/api/candidates/jobs/{job['id']}/applications?status=shortlisted",
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(row["status"] == "shortlisted" for row in body)


# ---------- F44.d.7 — bulk status endpoint ----------


async def _seed_three_apps(*, owner_id: UUID, job_id: UUID) -> list[Application]:
    apps: list[Application] = []
    async with SessionLocal() as session:
        for _ in range(3):
            candidate = Candidate(
                owner_id=owner_id,
                name=f"Cand-{uuid4()}",
                email=f"c-{uuid4()}@x.com",
            )
            session.add(candidate)
            await session.flush()
            app = Application(
                candidate_id=candidate.id,
                job_id=job_id,
                status=ApplicationStatus.NEW,
                score=0.5,
            )
            session.add(app)
            apps.append(app)
        await session.commit()
        for app in apps:
            await session.refresh(app)
    return apps


async def test_bulk_update_unauthenticated(client) -> None:
    response = await client.patch(
        "/api/candidates/applications/bulk-status",
        json={"application_ids": [str(uuid4())], "status": "shortlisted"},
    )
    assert response.status_code == 401


async def test_bulk_update_empty_list_422(client, hr_token, auth_headers) -> None:
    response = await client.patch(
        "/api/candidates/applications/bulk-status",
        json={"application_ids": [], "status": "shortlisted"},
        headers=auth_headers(hr_token),
    )
    # min_length=1 on the schema — pydantic rejects at the edge.
    assert response.status_code == 422


async def test_bulk_update_missing_application_404(
    client, hr_token, hr_user, auth_headers
) -> None:
    job = await _create_job(client, hr_token, auth_headers, "Job for bulk")
    apps = await _seed_three_apps(owner_id=hr_user.id, job_id=UUID(job["id"]))
    # Mix of real + bogus ids → whole batch rejects.
    bogus = uuid4()

    response = await client.patch(
        "/api/candidates/applications/bulk-status",
        json={
            "application_ids": [str(apps[0].id), str(bogus)],
            "status": "shortlisted",
        },
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 404

    # Nothing was flipped — atomicity guarantee.
    async with SessionLocal() as session:
        refreshed = await session.get(Application, apps[0].id)
        assert refreshed.status is ApplicationStatus.NEW


async def test_owner_can_bulk_shortlist(
    client, hr_token, hr_user, auth_headers
) -> None:
    job = await _create_job(client, hr_token, auth_headers, "Bulk shortlist")
    apps = await _seed_three_apps(owner_id=hr_user.id, job_id=UUID(job["id"]))

    response = await client.patch(
        "/api/candidates/applications/bulk-status",
        json={
            "application_ids": [str(a.id) for a in apps],
            "status": "shortlisted",
        },
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["updated"]) == 3
    assert all(row["status"] == "shortlisted" for row in body["updated"])
    # Order preserved from request.
    assert [row["id"] for row in body["updated"]] == [str(a.id) for a in apps]

    # DB reflects the change for every row.
    async with SessionLocal() as session:
        for app in apps:
            refreshed = await session.get(Application, app.id)
            assert refreshed.status is ApplicationStatus.SHORTLISTED


async def test_other_hr_cannot_bulk_update(
    client, hr_token, hr_user, auth_headers
) -> None:
    job = await _create_job(client, hr_token, auth_headers, "HR A's bulk job")
    apps = await _seed_three_apps(owner_id=hr_user.id, job_id=UUID(job["id"]))

    token_b = await _second_hr_token(client)

    response = await client.patch(
        "/api/candidates/applications/bulk-status",
        json={
            "application_ids": [str(a.id) for a in apps],
            "status": "shortlisted",
        },
        headers=auth_headers(token_b),
    )
    assert response.status_code == 403

    # No partial mutation.
    async with SessionLocal() as session:
        for app in apps:
            refreshed = await session.get(Application, app.id)
            assert refreshed.status is ApplicationStatus.NEW


async def test_admin_can_bulk_update_any_job(
    client, hr_token, hr_user, admin_token, auth_headers
) -> None:
    job = await _create_job(client, hr_token, auth_headers, "Admin bulk bypass")
    apps = await _seed_three_apps(owner_id=hr_user.id, job_id=UUID(job["id"]))

    response = await client.patch(
        "/api/candidates/applications/bulk-status",
        json={
            "application_ids": [str(a.id) for a in apps],
            "status": "rejected",
        },
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    assert all(row["status"] == "rejected" for row in response.json()["updated"])


async def test_bulk_update_dedupes_request(
    client, hr_token, hr_user, auth_headers
) -> None:
    """Duplicate ids in the request collapse to one DB row. Response
    keeps one entry per unique id in request order."""
    job = await _create_job(client, hr_token, auth_headers, "Dedup bulk")
    apps = await _seed_three_apps(owner_id=hr_user.id, job_id=UUID(job["id"]))
    duplicated = [str(apps[0].id), str(apps[0].id), str(apps[1].id)]

    response = await client.patch(
        "/api/candidates/applications/bulk-status",
        json={"application_ids": duplicated, "status": "shortlisted"},
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["updated"]) == 2
    assert [row["id"] for row in body["updated"]] == [
        str(apps[0].id),
        str(apps[1].id),
    ]
