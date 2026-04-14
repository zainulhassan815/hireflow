"""Shared async Redis client."""

from __future__ import annotations

from redis.asyncio import Redis, from_url

from app.core.config import settings

redis_client: Redis = from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
)


async def get_redis() -> Redis:
    """FastAPI dependency returning the shared Redis client."""
    return redis_client
