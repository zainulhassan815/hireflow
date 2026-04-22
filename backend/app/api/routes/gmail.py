"""Gmail OAuth connect/callback/list/sync/disconnect endpoints.

A user may hold multiple connections (F53). The ``/connections``
sub-resource models that: list, per-id sync, per-id disconnect.
``/authorize`` and ``/callback`` stay user-scoped (there's exactly one
OAuth flow in flight at a time per user; the callback routes into the
right ``(user_id, gmail_email)`` row via Google's userinfo).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, GmailServiceDep
from app.core.config import settings
from app.domain.exceptions import GmailAuthError, NotFound
from app.schemas.errors import ErrorResponse
from app.schemas.gmail import (
    GmailAuthorizeResponse,
    GmailConnection,
    GmailSyncTriggerResponse,
)

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
        "stored in Redis (10-minute TTL) and verified on callback. Use "
        "this endpoint for every new mailbox — connecting a different "
        "Google account adds a row rather than overwriting the previous "
        "one."
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
        "for tokens, verifies ``state``, and upserts a connection row keyed "
        "by ``(user_id, gmail_email)``. On success, redirects the browser "
        "back to the frontend settings page with ``?gmail=connected``. On "
        "error, redirects with ``?gmail=error&reason=<code>``."
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
    "/connections",
    response_model=list[GmailConnection],
    summary="List connected Gmail accounts",
    description=(
        "Returns every Gmail connection the current user holds, ordered "
        "oldest first. An empty list means no mailbox is connected yet."
    ),
    responses={401: {"model": ErrorResponse, "description": "Not authenticated"}},
)
async def list_gmail_connections(
    current_user: CurrentUser, gmail: GmailServiceDep
) -> list[GmailConnection]:
    connections = await gmail.list_connections(current_user.id)
    return [
        GmailConnection(
            id=c.id,
            gmail_email=c.gmail_email,
            connected_at=c.created_at,
            last_synced_at=c.last_synced_at,
            scopes=c.scopes,
        )
        for c in connections
    ]


@router.post(
    "/connections/{connection_id}/sync",
    response_model=GmailSyncTriggerResponse,
    status_code=202,
    summary="Trigger a Gmail sync now",
    description=(
        "Enqueues an immediate sync for the identified connection. "
        "Returns 202; the sync runs asynchronously in the worker. Poll "
        "``GET /api/auth/gmail/connections`` to watch ``last_synced_at`` "
        "update when it finishes."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        404: {
            "model": ErrorResponse,
            "description": "Connection not found or not owned by the current user",
        },
    },
)
async def gmail_sync_now(
    connection_id: UUID, current_user: CurrentUser, gmail: GmailServiceDep
) -> GmailSyncTriggerResponse:
    connection = await gmail.get_connection_for_user(current_user.id, connection_id)
    if connection is None:
        raise NotFound("Gmail connection not found.")

    # Import inside the handler: the worker package loads Celery eagerly,
    # which we don't want at FastAPI import time in environments that
    # haven't configured Redis yet (e.g. migration scripts).
    from app.worker.tasks import sync_gmail_connection

    sync_gmail_connection.delay(str(connection.id))
    return GmailSyncTriggerResponse(connection_id=connection.id)


@router.delete(
    "/connections/{connection_id}",
    status_code=204,
    summary="Disconnect a Gmail account",
    description=(
        "Revokes the stored refresh token with Google and removes the "
        "identified connection row. Safe to call even if Google is "
        "momentarily unreachable — the local connection is still deleted. "
        "Other connections owned by the user are untouched."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        404: {
            "model": ErrorResponse,
            "description": "Connection not found or not owned by the current user",
        },
    },
)
async def gmail_disconnect(
    connection_id: UUID,
    request: Request,
    current_user: CurrentUser,
    gmail: GmailServiceDep,
) -> None:
    client = request.client
    ip = client.host if client else None
    await gmail.disconnect(current_user.id, connection_id, ip_address=ip)
