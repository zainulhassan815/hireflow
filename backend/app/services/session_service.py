"""Token-pair issuance, refresh-rotation, and logout."""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.protocols import (
    RevocationStore,
    TokenIssuer,
    TokenType,
)
from app.domain.exceptions import InvalidToken
from app.models import User
from app.repositories.user import UserRepository


@dataclass(frozen=True, slots=True)
class TokenPair:
    access: str
    refresh: str


class SessionService:
    def __init__(
        self,
        users: UserRepository,
        tokens: TokenIssuer,
        revocation: RevocationStore,
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._revocation = revocation

    def issue(self, user: User) -> TokenPair:
        return TokenPair(
            access=self._tokens.issue_access(user.id, {"role": user.role.value}),
            refresh=self._tokens.issue_refresh(user.id),
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Rotate: revoke the presented refresh token, issue a new pair."""
        payload = self._tokens.decode(refresh_token, TokenType.REFRESH)

        if await self._revocation.is_revoked(payload.jti):
            raise InvalidToken("Invalid or expired refresh token.")

        user = await self._users.get(payload.sub)
        if user is None or not user.is_active:
            raise InvalidToken("Invalid or expired refresh token.")

        await self._revocation.revoke(payload.jti, payload.remaining_ttl_seconds)
        return self.issue(user)

    async def logout(self, refresh_token: str) -> None:
        """Revoke the presented refresh token. Idempotent for undecodable input."""
        try:
            payload = self._tokens.decode(refresh_token, TokenType.REFRESH)
        except InvalidToken:
            # Garbage in → no-op out: a token we can't identify can't cause harm.
            return
        await self._revocation.revoke(payload.jti, payload.remaining_ttl_seconds)
