"""Gmail OAuth connect + disconnect flow through the HTTP layer.

Uses respx to mock Google's token / userinfo / revoke endpoints;
everything else (state CSRF, DB upsert, activity log) runs real.
"""

from __future__ import annotations

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
    # state is present and non-trivial
    assert "state=" in url
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
    # 1. Begin authorization to get a real state key in Redis.
    begin = await client.post(
        "/api/auth/gmail/authorize", headers=auth_headers(admin_token)
    )
    state = begin.json()["authorize_url"].split("state=", 1)[1].split("&")[0]

    # 2. Mock Google's token exchange + userinfo.
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json=EXCHANGE_RESPONSE)
    )
    respx.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
        return_value=httpx.Response(200, json=USERINFO_RESPONSE)
    )

    # 3. Hit the callback as if Google just redirected.
    callback = await client.get(
        f"/api/auth/gmail/callback?code=test-code&state={state}",
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "gmail=connected" in callback.headers["location"]

    # 4. Connection row exists with encrypted refresh token.
    from sqlalchemy import select, text

    from app.core.db import SessionLocal
    from app.models import GmailConnection

    async with SessionLocal() as session:
        conn = (await session.execute(select(GmailConnection))).scalar_one()
        assert conn.user_id == admin_user.id
        assert conn.gmail_email == "candidate-source@example.com"
        # refresh_token round-trips through EncryptedString:
        assert conn.refresh_token == "test-refresh-token"

        # And on disk the column is ciphertext, not plaintext.
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


@respx.mock
async def test_disconnect_removes_row_and_calls_revoke(
    client, admin_token, auth_headers, admin_user
) -> None:
    # Seed a connection via the real upsert path so the factory
    # matches what the UI would produce.
    from app.core.db import SessionLocal
    from app.repositories.gmail_connection import GmailConnectionRepository

    async with SessionLocal() as session:
        await GmailConnectionRepository(session).upsert(
            user_id=admin_user.id,
            gmail_email="already-connected@example.com",
            refresh_token="cached-refresh-token",
            scopes=["openid", "email"],
        )

    revoke_mock = respx.post("https://oauth2.googleapis.com/revoke").mock(
        return_value=httpx.Response(200)
    )

    response = await client.delete("/api/auth/gmail", headers=auth_headers(admin_token))
    assert response.status_code == 204
    assert revoke_mock.called

    # Row is gone.
    from sqlalchemy import func, select

    from app.models import GmailConnection

    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(GmailConnection))
    assert count == 0
