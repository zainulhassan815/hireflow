"""Forgot-password and reset-password flow."""

from __future__ import annotations

from app.adapters.protocols import EmailSender, PasswordHasher, ResetTokenStore
from app.domain.exceptions import InvalidToken
from app.repositories.user import UserRepository


class PasswordResetService:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        tokens: ResetTokenStore,
        email: EmailSender,
        *,
        token_ttl_seconds: int,
        reset_url_template: str = "/reset-password?token={token}",
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        self._email = email
        self._ttl = token_ttl_seconds
        self._url_template = reset_url_template

    async def request_reset(self, email: str) -> None:
        """Issue + email a reset token if the account exists. Silent otherwise
        so this endpoint can't enumerate registered addresses.
        """
        user = await self._users.get_by_email(email)
        if user is None or not user.is_active:
            return
        token = await self._tokens.issue(user.id, self._ttl)
        reset_url = self._url_template.format(token=token)
        await self._email.send_password_reset(user.email, reset_url)

    async def reset(self, token: str, new_password: str) -> None:
        user_id = await self._tokens.consume(token)
        if user_id is None:
            raise InvalidToken("Invalid or expired reset token.")
        user = await self._users.get(user_id)
        if user is None or not user.is_active:
            raise InvalidToken("Invalid or expired reset token.")
        user.hashed_password = self._hasher.hash(new_password)
        await self._users.save(user)
