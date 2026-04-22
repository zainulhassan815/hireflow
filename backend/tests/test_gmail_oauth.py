"""Gmail OAuth connect + disconnect flow through the HTTP layer.

Uses respx to mock Google's token / userinfo / revoke endpoints;
everything else (state CSRF, DB upsert, activity log) runs real.

Covers F53 multi-account behaviour: listing, re-auth same address,
auth different address, owner scoping on disconnect/sync.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
import respx

from tests.gmail_responses import EXCHANGE_RESPONSE, USERINFO_RESPONSE

pytestmark = pytest.mark.asyncio


GMAIL_CLIENT_ID = "test-client-id.apps.googleusercontent.com"


@pytest.fixture(autouse=True)
def gmail_oauth_configured(monkeypatch):
    """Populate Gmail OAuth settings so ``get_gmail_service`` wires up."""
    from app.adapters.gmail_oauth import GoogleGmailOAuth
    from app.api import deps

    monkeypatch.setattr(deps.settings, "gmail_client_id", GMAIL_CLIENT_ID)
    from pydantic import SecretStr

    monkeypatch.setattr(
        deps.settings, "gmail_client_secret", SecretStr("test-client-secret")
    )
    monkeypatch.setattr(
        deps.settings,
        "gmail_redirect_uri",
        "http://localhost:8080/api/auth/gmail/callback",
    )
    monkeypatch.setattr(
        deps,
        "_gmail_oauth",
        GoogleGmailOAuth(
            client_id=GMAIL_CLIENT_ID,
            client_secret="test-client-secret",
            redirect_uri="http://localhost:8080/api/auth/gmail/callback",
        ),
    )


async def _state_for(client, token, headers) -> str:
    response = await client.post("/api/auth/gmail/authorize", headers=headers(token))
    return response.json()["authorize_url"].split("state=", 1)[1].split("&")[0]


def _mock_google(email: str) -> None:
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json=EXCHANGE_RESPONSE)
    )
    respx.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
        return_value=httpx.Response(200, json={**USERINFO_RESPONSE, "email": email})
    )


async def test_authorize_returns_google_url_with_state(
    client, admin_token, auth_headers
) -> None:
    response = await client.post(
        "/api/auth/gmail/authorize", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    url = response.json()["authorize_url"]
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert f"client_id={GMAIL_CLIENT_ID}" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    state_value = url.split("state=", 1)[1].split("&")[0]
    assert len(state_value) > 20


async def test_authorize_stores_state_in_redis(
    client, admin_token, auth_headers, admin_user
) -> None:
    response = await client.post(
        "/api/auth/gmail/authorize", headers=auth_headers(admin_token)
    )
    state = response.json()["authorize_url"].split("state=", 1)[1].split("&")[0]

    from app.core.redis import redis_client

    stored = await redis_client.get(f"gmail_oauth_state:{state}")
    assert stored == str(admin_user.id)


@respx.mock
async def test_callback_happy_path_stores_connection_and_redirects(
    client, admin_token, auth_headers, admin_user
) -> None:
    state = await _state_for(client, admin_token, auth_headers)
    _mock_google("candidate-source@example.com")

    callback = await client.get(
        f"/api/auth/gmail/callback?code=test-code&state={state}",
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "gmail=connected" in callback.headers["location"]

    from sqlalchemy import select, text

    from app.core.db import SessionLocal
    from app.models import GmailConnection

    async with SessionLocal() as session:
        conn = (await session.execute(select(GmailConnection))).scalar_one()
        assert conn.user_id == admin_user.id
        assert conn.gmail_email == "candidate-source@example.com"
        assert conn.refresh_token == "test-refresh-token"

        raw = await session.scalar(
            text(
                "SELECT refresh_token FROM gmail_connections WHERE id = :i"
            ).bindparams(i=conn.id)
        )
    assert b"test-refresh-token" not in bytes(raw)


async def test_callback_with_bogus_state_redirects_to_error(client) -> None:
    callback = await client.get(
        "/api/auth/gmail/callback?code=whatever&state=not-a-real-state",
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "gmail=error" in callback.headers["location"]
    assert "reason=invalid_state" in callback.headers["location"]


async def test_callback_with_user_denied_redirects_to_denied(client) -> None:
    callback = await client.get(
        "/api/auth/gmail/callback?error=access_denied",
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "reason=denied" in callback.headers["location"]


async def test_list_connections_empty(client, admin_token, auth_headers) -> None:
    response = await client.get(
        "/api/auth/gmail/connections", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_list_connections_returns_owned_rows(
    client, admin_token, auth_headers, admin_user
) -> None:
    from app.core.db import SessionLocal
    from app.repositories.gmail_connection import GmailConnectionRepository

    async with SessionLocal() as session:
        repo = GmailConnectionRepository(session)
        await repo.upsert(
            user_id=admin_user.id,
            gmail_email="work@example.com",
            refresh_token="rt-work",
            scopes=["openid", "email"],
        )
        await repo.upsert(
            user_id=admin_user.id,
            gmail_email="personal@example.com",
            refresh_token="rt-personal",
            scopes=["openid", "email"],
        )

    response = await client.get(
        "/api/auth/gmail/connections", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    emails = [row["gmail_email"] for row in body]
    # Oldest-first: work@ was created before personal@.
    assert emails == ["work@example.com", "personal@example.com"]
    for row in body:
        assert "refresh_token" not in row
        assert row["connected_at"]
        assert row["last_synced_at"] is None


@respx.mock
async def test_reauthorize_same_email_updates_existing_row(
    client, admin_token, auth_headers, admin_user
) -> None:
    # First auth.
    state_one = await _state_for(client, admin_token, auth_headers)
    _mock_google("only@example.com")
    first = await client.get(
        f"/api/auth/gmail/callback?code=test-code&state={state_one}",
        follow_redirects=False,
    )
    assert first.status_code == 302

    # Second auth for the same Gmail address.
    state_two = await _state_for(client, admin_token, auth_headers)
    _mock_google("only@example.com")
    second = await client.get(
        f"/api/auth/gmail/callback?code=test-code&state={state_two}",
        follow_redirects=False,
    )
    assert second.status_code == 302

    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.models import GmailConnection

    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(GmailConnection))
    assert count == 1


@respx.mock
async def test_reauthorize_different_email_adds_row(
    client, admin_token, auth_headers, admin_user
) -> None:
    state_one = await _state_for(client, admin_token, auth_headers)
    _mock_google("first@example.com")
    await client.get(
        f"/api/auth/gmail/callback?code=test-code&state={state_one}",
        follow_redirects=False,
    )

    state_two = await _state_for(client, admin_token, auth_headers)
    _mock_google("second@example.com")
    await client.get(
        f"/api/auth/gmail/callback?code=test-code&state={state_two}",
        follow_redirects=False,
    )

    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.models import GmailConnection

    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(GmailConnection))
    assert count == 2


@respx.mock
async def test_disconnect_one_leaves_the_other(
    client, admin_token, auth_headers, admin_user
) -> None:
    from app.core.db import SessionLocal
    from app.models import ActivityLog, GmailConnection
    from app.repositories.gmail_connection import GmailConnectionRepository

    async with SessionLocal() as session:
        repo = GmailConnectionRepository(session)
        first = await repo.upsert(
            user_id=admin_user.id,
            gmail_email="first@example.com",
            refresh_token="rt-1",
            scopes=["openid", "email"],
        )
        second = await repo.upsert(
            user_id=admin_user.id,
            gmail_email="second@example.com",
            refresh_token="rt-2",
            scopes=["openid", "email"],
        )
        first_id = first.id
        second_id = second.id

    respx.post("https://oauth2.googleapis.com/revoke").mock(
        return_value=httpx.Response(200)
    )

    response = await client.delete(
        f"/api/auth/gmail/connections/{first_id}",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 204

    from sqlalchemy import select

    async with SessionLocal() as session:
        remaining = (await session.execute(select(GmailConnection))).scalars().all()
        assert [c.id for c in remaining] == [second_id]

        # Activity log cites the correct connection id.
        log_rows = (
            (
                await session.execute(
                    select(ActivityLog).where(ActivityLog.action == "gmail_disconnect")
                )
            )
            .scalars()
            .all()
        )
        assert any(row.resource_id == str(first_id) for row in log_rows)


async def test_disconnect_other_users_connection_404(
    client, admin_token, auth_headers, admin_user
) -> None:
    """A user cannot disconnect a connection owned by another user.

    Same 404 shape as "genuinely not found" so existence is not
    disclosed across tenants.
    """
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models import User
    from app.repositories.gmail_connection import GmailConnectionRepository

    async with SessionLocal() as session:
        # Seed a second user and give them a connection.
        from app.models import UserRole

        other = User(
            email=f"other-{uuid4()}@example.com",
            hashed_password="$argon2id$v=19$not-a-real-hash",
            role=UserRole.HR,
            is_active=True,
        )
        session.add(other)
        await session.commit()
        await session.refresh(other)
        other_id = other.id

        other_conn = await GmailConnectionRepository(session).upsert(
            user_id=other_id,
            gmail_email="other@example.com",
            refresh_token="rt-other",
            scopes=["openid", "email"],
        )
        other_conn_id = other_conn.id

    response = await client.delete(
        f"/api/auth/gmail/connections/{other_conn_id}",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 404

    # Other user's row is untouched.
    async with SessionLocal() as session:
        from app.models import GmailConnection

        surviving = (
            await session.execute(
                select(GmailConnection).where(GmailConnection.id == other_conn_id)
            )
        ).scalar_one()
        assert surviving.user_id == other_id


async def test_disconnect_missing_connection_404(
    client, admin_token, auth_headers
) -> None:
    bogus = UUID("00000000-0000-0000-0000-000000000000")
    response = await client.delete(
        f"/api/auth/gmail/connections/{bogus}",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 404


async def test_sync_missing_connection_404(client, admin_token, auth_headers) -> None:
    bogus = UUID("00000000-0000-0000-0000-000000000000")
    response = await client.post(
        f"/api/auth/gmail/connections/{bogus}/sync",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 404


async def test_sync_other_users_connection_404(
    client, admin_token, auth_headers
) -> None:
    from uuid import uuid4

    from app.core.db import SessionLocal
    from app.models import User
    from app.repositories.gmail_connection import GmailConnectionRepository

    async with SessionLocal() as session:
        from app.models import UserRole

        other = User(
            email=f"other-{uuid4()}@example.com",
            hashed_password="$argon2id$v=19$not-a-real-hash",
            role=UserRole.HR,
            is_active=True,
        )
        session.add(other)
        await session.commit()
        await session.refresh(other)
        other_conn = await GmailConnectionRepository(session).upsert(
            user_id=other.id,
            gmail_email="other@example.com",
            refresh_token="rt-other",
            scopes=["openid", "email"],
        )
        other_conn_id = other_conn.id

    response = await client.post(
        f"/api/auth/gmail/connections/{other_conn_id}/sync",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 404
