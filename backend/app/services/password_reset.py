"""One-time password-reset tokens backed by Redis.

The plaintext token is a URL-safe random string sent via email; only its
SHA-256 hash is stored server-side. Tokens are single-use and auto-expire.
"""

from __future__ import annotations

import hashlib
import secrets
from uuid import UUID

from redis.asyncio import Redis

_KEY_PREFIX = "pw_reset:"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _key(token: str) -> str:
    return f"{_KEY_PREFIX}{_hash_token(token)}"


async def issue_reset_token(redis: Redis, user_id: UUID, ttl_seconds: int) -> str:
    token = secrets.token_urlsafe(32)
    await redis.set(_key(token), str(user_id), ex=ttl_seconds)
    return token


async def consume_reset_token(redis: Redis, token: str) -> UUID | None:
    """Atomically read + delete the token. Returns the user id or None."""
    key = _key(token)
    async with redis.pipeline(transaction=True) as pipe:
        pipe.get(key)
        pipe.delete(key)
        raw_user_id, _ = await pipe.execute()
    if raw_user_id is None:
        return None
    return UUID(raw_user_id)
