"""Account registration and credential verification."""

from __future__ import annotations

from app.adapters.protocols import PasswordHasher
from app.domain.exceptions import AccountDisabled, InvalidCredentials
from app.models import User, UserRole
from app.repositories.user import UserRepository


class AuthService:
    def __init__(self, users: UserRepository, hasher: PasswordHasher) -> None:
        self._users = users
        self._hasher = hasher

    async def register(self, *, email: str, password: str, full_name: str) -> User:
        return await self._users.create(
            email=email,
            hashed_password=self._hasher.hash(password),
            full_name=full_name,
            role=UserRole.HR,
        )

    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self._users.get_by_email(email)

        # Always spend the verify cost so "no such user" and "wrong password"
        # are indistinguishable by timing.
        if user is None:
            self._hasher.verify(password, _DUMMY_HASH)
            raise InvalidCredentials("Invalid email or password.")

        if not self._hasher.verify(password, user.hashed_password):
            raise InvalidCredentials("Invalid email or password.")

        if not user.is_active:
            raise AccountDisabled("Account is disabled.")

        # Opportunistic upgrade when Argon2 parameters tighten.
        if self._hasher.needs_rehash(user.hashed_password):
            user.hashed_password = self._hasher.hash(password)
            await self._users.save(user)

        return user


# A known-valid Argon2id hash whose plaintext is unguessable. Verifying
# against it burns CPU in the "user not found" branch to equalize latency.
_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "c29tZXNhbHR2YWx1ZQ$Z1qNTf+7M+UqJ7Id9xy4s6cT7ZQJ3XA5VJ7pVlDbXoE"
)
