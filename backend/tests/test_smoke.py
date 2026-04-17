"""First test — verifies the harness itself works end-to-end.

If this fails, every other test will fail. Keep it trivial.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_health_endpoint_returns_200(client) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200


async def test_database_is_clean_between_tests(client, admin_user) -> None:
    """Seed a user; the next test should see zero users thanks to TRUNCATE."""
    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.models import User

    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(User))
        assert count == 1


async def test_database_is_clean_on_next_test() -> None:
    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.models import User

    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(User))
        assert count == 0, "previous test's admin_user leaked into this one"
