"""Redis-backed JTI revocation list."""

from __future__ import annotations

from redis.asyncio import Redis

_KEY_PREFIX = "revoked_jti:"


class RedisRevocationStore:
    """`RevocationStore` protocol implementation backed by Redis.

    Revoked JTIs are stored as keys with a TTL equal to the token's remaining
    lifetime; expired entries self-clean, no sweeper required.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def revoke(self, jti: str, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            # Token's already expired — revoking it adds nothing.
            return
        await self._redis.set(self._key(jti), "1", ex=ttl_seconds)

    async def is_revoked(self, jti: str) -> bool:
        return bool(await self._redis.exists(self._key(jti)))

    @staticmethod
    def _key(jti: str) -> str:
        return f"{_KEY_PREFIX}{jti}"
