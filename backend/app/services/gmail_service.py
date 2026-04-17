"""Gmail OAuth service.

Orchestrates the three moving parts of the connect flow:

1. ``begin_authorization`` — mint a CSRF ``state`` token, store it in
   Redis keyed by the authenticating user, and return the Google
   consent URL.
2. ``complete_authorization`` — pop the state, exchange the code for
   tokens, learn the user's Gmail address, upsert the connection row.
3. ``disconnect`` — revoke the refresh token with Google, delete the
   row.

Both connect and disconnect emit ``ActivityLog`` entries so an audit
can always answer who connected what and when.
"""

from __future__ import annotations

import logging
import secrets
from uuid import UUID

from redis.asyncio import Redis

from app.adapters.protocols import GmailOAuth
from app.domain.exceptions import GmailAuthError, NotFound
from app.models import ActivityAction, GmailConnection
from app.repositories.gmail_connection import GmailConnectionRepository
from app.services.activity_service import ActivityService

logger = logging.getLogger(__name__)

_STATE_PREFIX = "gmail_oauth_state:"
_STATE_TTL_SECONDS = 600  # 10 minutes


class GmailService:
    def __init__(
        self,
        *,
        oauth: GmailOAuth,
        connections: GmailConnectionRepository,
        redis: Redis,
        activity: ActivityService,
    ) -> None:
        self._oauth = oauth
        self._connections = connections
        self._redis = redis
        self._activity = activity

    async def begin_authorization(self, user_id: UUID) -> str:
        state = secrets.token_urlsafe(32)
        await self._redis.set(
            _STATE_PREFIX + state, str(user_id), ex=_STATE_TTL_SECONDS
        )
        return self._oauth.build_authorize_url(state)

    async def complete_authorization(
        self, *, code: str, state: str, ip_address: str | None = None
    ) -> GmailConnection:
        user_id = await self._pop_state(state)
        if user_id is None:
            raise GmailAuthError("OAuth state is invalid or has expired.")

        tokens = await self._oauth.exchange_code(code)
        if not tokens.refresh_token:
            # Google only returns a refresh_token with access_type=offline
            # + prompt=consent. The adapter sets both, so a missing token
            # here is a genuine Google-side failure.
            raise GmailAuthError(
                "Google did not return a refresh token. Please try again."
            )

        gmail_email = await self._oauth.fetch_email(tokens.access_token)
        scopes = tokens.scope.split()

        connection = await self._connections.upsert(
            user_id=user_id,
            gmail_email=gmail_email,
            refresh_token=tokens.refresh_token,
            scopes=scopes,
        )
        await self._activity.log(
            actor_id=user_id,
            action=ActivityAction.GMAIL_CONNECT,
            resource_type="gmail_connection",
            resource_id=str(connection.id),
            detail=f"{gmail_email} scopes={','.join(scopes)}",
            ip_address=ip_address,
        )
        return connection

    async def disconnect(self, user_id: UUID, *, ip_address: str | None = None) -> None:
        connection = await self._connections.get_by_user(user_id)
        if connection is None:
            raise NotFound("No Gmail connection to disconnect.")

        # Best-effort revoke. If Google is unreachable we still delete
        # the row — the refresh token is ciphertext locally, so losing
        # the ability to revoke server-side doesn't leave a usable
        # credential.
        await self._oauth.revoke(connection.refresh_token)

        gmail_email = connection.gmail_email
        await self._connections.delete(connection)

        await self._activity.log(
            actor_id=user_id,
            action=ActivityAction.GMAIL_DISCONNECT,
            resource_type="gmail_connection",
            resource_id=str(connection.id),
            detail=gmail_email,
            ip_address=ip_address,
        )

    async def get_connection(self, user_id: UUID) -> GmailConnection | None:
        return await self._connections.get_by_user(user_id)

    async def _pop_state(self, state: str) -> UUID | None:
        key = _STATE_PREFIX + state
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.get(key)
            pipe.delete(key)
            raw_user_id, _ = await pipe.execute()
        if raw_user_id is None:
            return None
        return UUID(raw_user_id)
