"""Google OAuth 2.0 client for Gmail.

A thin async wrapper over Google's four OAuth endpoints using ``httpx``.
The SDK (google-auth / google-api-python-client) is intentionally avoided
— it pulls in a large dependency surface for what amounts to four HTTP
calls.

Scopes requested at authorize time bundle everything Gmail-integration
features need so the user sees one consent screen:

* ``openid email`` — we read the connected Gmail address.
* ``gmail.readonly`` — required by F51 (resume sync).
* ``gmail.send`` — required by F52 (follow-up emails).
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from app.adapters.protocols import OAuthTokens

logger = logging.getLogger(__name__)

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


class GoogleGmailOAuth:
    """Google OAuth client for Gmail scopes."""

    def __init__(
        self, *, client_id: str, client_secret: str, redirect_uri: str
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def build_authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": " ".join(_SCOPES),
            "access_type": "offline",
            "prompt": "consent",  # force refresh_token on every consent
            "state": state,
        }
        return f"{_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OAuthTokens:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                _TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": self._redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        return _parse_tokens(response)

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                _TOKEN_URL,
                data={
                    "refresh_token": refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                },
            )
        return _parse_tokens(response)

    async def revoke(self, token: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(_REVOKE_URL, data={"token": token})
        # 200 = revoked; 400 = token already invalid. Either is a success
        # from the caller's perspective ("token will not work after this").
        if response.status_code not in (200, 400):
            logger.warning(
                "gmail revoke failed: status=%s body=%s",
                response.status_code,
                response.text[:200],
            )

    async def fetch_email(self, access_token: str) -> str:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                _USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        response.raise_for_status()
        email = response.json().get("email")
        if not isinstance(email, str) or not email:
            raise RuntimeError("userinfo response missing email")
        return email


def _parse_tokens(response: httpx.Response) -> OAuthTokens:
    if response.status_code != 200:
        # Don't leak the response body: Google sometimes echoes the
        # client_id/secret back on certain failures.
        logger.warning(
            "gmail token endpoint returned %s: %s",
            response.status_code,
            response.json().get("error", "unknown_error")
            if response.headers.get("content-type", "").startswith("application/json")
            else "non-json",
        )
        raise RuntimeError(f"google token exchange failed: {response.status_code}")

    payload = response.json()
    return OAuthTokens(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_in=int(payload.get("expires_in", 0)),
        scope=payload.get("scope", ""),
    )
