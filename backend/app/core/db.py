from collections.abc import AsyncIterator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# ---------- Async (FastAPI) ----------

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async session scoped to the request."""
    async with SessionLocal() as session:
        yield session


# ---------- Sync (Celery workers) ----------

_sync_url = settings.database_url.replace("+asyncpg", "+psycopg2")

sync_engine = create_engine(
    _sync_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
    autoflush=False,
)


def get_sync_db() -> Session:
    """Return a plain synchronous session for use outside the event loop."""
    return SyncSessionLocal()
