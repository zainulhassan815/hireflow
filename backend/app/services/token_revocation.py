"""Refresh-token revocation list backed by Redis.

A token is revoked by storing its `jti` claim as a Redis key with a TTL equal
to the token's remaining lifetime. Once the token would naturally expire, the
Redis entry goes away on its own — no cleanup job required.
"""

from __future__ import annotations

from redis.asyncio import Redis

_REVOKED_KEY_PREFIX = "revoked_jti:"


def _key(jti: str) -> str:
    return f"{_REVOKED_KEY_PREFIX}{jti}"


async def revoke_jti(redis: Redis, jti: str, ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        # Token is already expired; nothing worth persisting.
        return
    await redis.set(_key(jti), "1", ex=ttl_seconds)


async def is_jti_revoked(redis: Redis, jti: str) -> bool:
    return bool(await redis.exists(_key(jti)))
