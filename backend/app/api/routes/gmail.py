"""Gmail OAuth connect/callback/disconnect/status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, GmailServiceDep
from app.core.config import settings
from app.domain.exceptions import GmailAuthError
from app.schemas.errors import ErrorResponse
from app.schemas.gmail import GmailAuthorizeResponse, GmailConnectionStatus

router = APIRouter()


def _frontend_base() -> str:
    """First entry in ``ALLOWED_ORIGINS`` is treated as the canonical frontend."""
    return settings.allowed_origins[0] if settings.allowed_origins else ""


@router.post(
    "/authorize",
    response_model=GmailAuthorizeResponse,
    summary="Begin Gmail OAuth flow",
    description=(
        "Returns a Google consent URL. The frontend should redirect the "
        "browser to this URL. Google will call the backend's callback "
        "endpoint when the user approves or denies. A CSRF ``state`` is "
        "stored in Redis (10-minute TTL) and verified on callback."
    ),
    responses={401: {"model": ErrorResponse, "description": "Not authenticated"}},
)
async def gmail_authorize(
    current_user: CurrentUser, gmail: GmailServiceDep
) -> GmailAuthorizeResponse:
    url = await gmail.begin_authorization(current_user.id)
    return GmailAuthorizeResponse(authorize_url=url)


@router.get(
    "/callback",
    summary="Gmail OAuth callback",
    description=(
        "Endpoint Google redirects to after consent. Exchanges the ``code`` "
        "for tokens, verifies ``state``, and stores an encrypted refresh "
        "token. On success, redirects the browser back to the frontend "
        "settings page with ``?gmail=connected``. On error, redirects with "
        "``?gmail=error&reason=<code>``."
    ),
    include_in_schema=False,  # browser-only, not called by API consumers
)
async def gmail_callback(
    request: Request,
    gmail: GmailServiceDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings_url = f"{_frontend_base()}/settings"

    if error:  # user denied consent on Google's screen
        return RedirectResponse(
            url=f"{settings_url}?gmail=error&reason=denied", status_code=302
        )
    if not code or not state:
        return RedirectResponse(
            url=f"{settings_url}?gmail=error&reason=missing_params", status_code=302
        )

    client = request.client
    ip = client.host if client else None

    try:
        await gmail.complete_authorization(code=code, state=state, ip_address=ip)
    except GmailAuthError as exc:
        reason = "invalid_state" if "state" in str(exc).lower() else "exchange_failed"
        return RedirectResponse(
            url=f"{settings_url}?gmail=error&reason={reason}", status_code=302
        )
    except Exception:
        return RedirectResponse(
            url=f"{settings_url}?gmail=error&reason=exchange_failed", status_code=302
        )

    return RedirectResponse(url=f"{settings_url}?gmail=connected", status_code=302)


@router.get(
    "",
    response_model=GmailConnectionStatus,
    summary="Get Gmail connection status",
    responses={401: {"model": ErrorResponse, "description": "Not authenticated"}},
)
async def gmail_status(
    current_user: CurrentUser, gmail: GmailServiceDep
) -> GmailConnectionStatus:
    connection = await gmail.get_connection(current_user.id)
    if connection is None:
        return GmailConnectionStatus(connected=False)
    return GmailConnectionStatus(
        connected=True,
        gmail_email=connection.gmail_email,
        connected_at=connection.created_at,
        last_synced_at=connection.last_synced_at,
        scopes=connection.scopes,
    )


@router.delete(
    "",
    status_code=204,
    summary="Disconnect Gmail",
    description=(
        "Revokes the stored refresh token with Google and removes the "
        "connection row. Safe to call even if Google is momentarily "
        "unreachable — the local connection is still deleted."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        404: {"model": ErrorResponse, "description": "No connection to disconnect"},
    },
)
async def gmail_disconnect(
    request: Request, current_user: CurrentUser, gmail: GmailServiceDep
) -> None:
    client = request.client
    ip = client.host if client else None
    await gmail.disconnect(current_user.id, ip_address=ip)
