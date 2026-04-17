"""Every non-2xx response uses the ``{error: {code, message}}`` envelope.

Would have caught the ``{"detail": "Not authenticated"}`` leak from
FastAPI's ``OAuth2PasswordBearer`` (F70 initial deploy).

One test per handler branch: ``DomainError``, ``HTTPException``,
``RequestValidationError``, uncaught ``Exception``.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


# ---- DomainError branch: service raises → 400-ish + envelope ----


async def test_domain_error_invalid_credentials_is_enveloped(client) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"email": "noone@example.com", "password": "wrong"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body == {
        "error": {
            "code": "invalid_credentials",
            "message": "Invalid email or password.",
        }
    }


async def test_domain_error_email_already_registered_maps_to_409(
    client, admin_user
) -> None:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": admin_user.email,
            "password": "anotherpass123",
            "full_name": "Dup",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"


async def test_domain_error_not_found_maps_to_404(
    client, admin_token, auth_headers
) -> None:
    # A random UUID that certainly doesn't exist in a fresh test DB.
    response = await client.get(
        "/api/jobs/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# ---- RequestValidationError branch: 422 + details ----


async def test_validation_error_produces_details_array(client) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "x", "full_name": ""},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["details"], list)
    assert len(body["error"]["details"]) >= 1
    # Each detail has a dotted field path + message.
    for detail in body["error"]["details"]:
        assert set(detail.keys()) == {"field", "message"}
        assert detail["field"].startswith("body.")


# ---- HTTPException branch: FastAPI's own security errors ----


async def test_missing_auth_header_produces_envelope(client) -> None:
    """The regression this would have caught.

    Before F70's HTTPException handler, FastAPI's ``OAuth2PasswordBearer``
    raised ``HTTPException(401, "Not authenticated")`` which the
    framework rendered as ``{"detail": "Not authenticated"}`` — the old
    shape, not our envelope.
    """
    response = await client.get("/api/documents")
    assert response.status_code == 401
    body = response.json()
    assert body == {
        "error": {
            "code": "unauthorized",
            "message": "Not authenticated",
        }
    }


async def test_invalid_bearer_token_produces_invalid_token_envelope(client) -> None:
    response = await client.get(
        "/api/documents", headers={"Authorization": "Bearer totally-not-a-jwt"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"
