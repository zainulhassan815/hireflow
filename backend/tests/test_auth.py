"""Auth flow: register, login, refresh, logout, token revocation.

These exercise the real ``AuthService`` / ``SessionService`` against a
real DB and Redis. Would catch:

* silent password-hash breakage (login works but shouldn't)
* JWT `jti` not recorded on logout (revoked token still works)
* refresh-then-reuse of the same refresh token (rotation not happening)
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


# ---- Register ----


async def test_register_returns_created_user_without_tokens(client) -> None:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "new-user@test.hireflow.io",
            "password": "correct-horse-battery",
            "full_name": "New User",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new-user@test.hireflow.io"
    assert body["full_name"] == "New User"
    assert body["role"] == "hr"
    # Register intentionally does not issue tokens; force a login next.
    assert "access_token" not in body


async def test_register_duplicate_email_is_409(client, admin_user) -> None:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": admin_user.email,
            "password": "anotherpass123",
            "full_name": "Dup",
        },
    )
    assert response.status_code == 409


# ---- Login ----


async def test_login_wrong_password_returns_invalid_credentials(
    client, admin_user
) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "nope"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_login_returns_access_and_refresh(client, admin_user) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "admin-test-password"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"].lower() == "bearer"


# ---- Protected endpoints ----


async def test_me_endpoint_round_trips(
    client, admin_token, admin_user, auth_headers
) -> None:
    response = await client.get("/api/auth/me", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert response.json()["email"] == admin_user.email


# ---- Refresh rotation + revocation ----


async def test_refresh_issues_a_new_pair_and_revokes_the_old(
    client, admin_user
) -> None:
    login = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "admin-test-password"},
    )
    first = login.json()

    refresh = await client.post(
        "/api/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert refresh.status_code == 200
    second = refresh.json()
    # Each refresh yields a fresh access + refresh token pair.
    assert second["access_token"] != first["access_token"]
    assert second["refresh_token"] != first["refresh_token"]

    # Old refresh token is now denylisted; re-using it 401s.
    replay = await client.post(
        "/api/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "invalid_token"


async def test_logout_revokes_refresh_token(client, admin_user) -> None:
    login = (
        await client.post(
            "/api/auth/login",
            json={
                "email": admin_user.email,
                "password": "admin-test-password",
            },
        )
    ).json()

    logout = await client.post(
        "/api/auth/logout", json={"refresh_token": login["refresh_token"]}
    )
    assert logout.status_code == 204

    # Denylist hit on refresh.
    replay = await client.post(
        "/api/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert replay.status_code == 401
