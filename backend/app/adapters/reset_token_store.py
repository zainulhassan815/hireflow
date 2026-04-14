"""Redis-backed one-time password-reset token store."""

from __future__ import annotations

import hashlib
import secrets
from uuid import UUID

from redis.asyncio import Redis

_KEY_PREFIX = "pw_reset:"


class RedisResetTokenStore:
    """`ResetTokenStore` protocol implementation.

    Stores SHA-256 of the token so a Redis dump can't leak usable plaintext.
    `consume` uses a transactional `GET + DEL` pipeline so two concurrent
    reset attempts can't both succeed.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def issue(self, user_id: UUID, ttl_seconds: int) -> str:
        token = secrets.token_urlsafe(32)
        await self._redis.set(self._key(token), str(user_id), ex=ttl_seconds)
        return token

    async def consume(self, token: str) -> UUID | None:
        key = self._key(token)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.get(key)
            pipe.delete(key)
            raw_user_id, _ = await pipe.execute()
        if raw_user_id is None:
            return None
        return UUID(raw_user_id)

    @staticmethod
    def _key(token: str) -> str:
        digest = hashlib.sha256(token.encode()).hexdigest()
        return f"{_KEY_PREFIX}{digest}"
