"""Resource-ownership enforcement across services.

HR users can only touch their own jobs/candidates/documents. Admin
bypasses ownership checks. Covers the ``Forbidden`` path through
``_ensure_access`` in the service layer — which F70 touched when
moving away from raw ``HTTPException``.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _create_job(client, token, auth_headers, title: str) -> dict:
    response = await client.post(
        "/api/jobs",
        json={
            "title": title,
            "description": "Nothing special.",
            "required_skills": ["python"],
            "experience_min": 0,
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_hr_cannot_read_another_hrs_job(
    client, auth_headers, hr_user, admin_user
) -> None:
    """HR A creates a job; HR B gets 403 trying to read it."""
    from app.adapters.argon2_hasher import Argon2Hasher
    from app.core.db import SessionLocal
    from app.models import UserRole
    from app.repositories.user import UserRepository

    # Seed a second HR user alongside the fixture's hr_user.
    async with SessionLocal() as session:
        await UserRepository(session).create(
            email="hr-b@test.hireflow.io",
            hashed_password=Argon2Hasher().hash("hr-b-password"),
            full_name="HR B",
            role=UserRole.HR,
        )

    token_a = (
        await client.post(
            "/api/auth/login",
            json={"email": "hr@test.hireflow.io", "password": "hr-test-password"},
        )
    ).json()["access_token"]
    token_b = (
        await client.post(
            "/api/auth/login",
            json={"email": "hr-b@test.hireflow.io", "password": "hr-b-password"},
        )
    ).json()["access_token"]

    job = await _create_job(client, token_a, auth_headers, "HR A's job")

    response = await client.get(f"/api/jobs/{job['id']}", headers=auth_headers(token_b))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_admin_can_read_any_users_job(
    client, auth_headers, hr_user, admin_token, hr_token
) -> None:
    """Admin bypasses ownership; should see HR's job without issue."""
    job = await _create_job(client, hr_token, auth_headers, "HR's private job")

    response = await client.get(
        f"/api/jobs/{job['id']}", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    assert response.json()["id"] == job["id"]


async def test_owner_can_read_own_job(client, auth_headers, hr_user, hr_token) -> None:
    """Sanity: the owner path isn't broken by the forbidden check."""
    job = await _create_job(client, hr_token, auth_headers, "Mine")

    response = await client.get(
        f"/api/jobs/{job['id']}", headers=auth_headers(hr_token)
    )
    assert response.status_code == 200
