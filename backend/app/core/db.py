from collections.abc import AsyncIterator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

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


# ---------- Async (Celery workers) ----------
#
# Celery tasks run async code via `asyncio.run`, which creates and tears
# down a fresh event loop per invocation. A pooled engine would cache
# asyncpg connections bound to the first loop and hand them back to the
# next task — asyncpg's internal Futures then raise "attached to a
# different loop". NullPool sidesteps this by opening a fresh connection
# per checkout and closing it on return, so nothing crosses loops.

worker_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
)

WorkerSessionLocal = async_sessionmaker(
    bind=worker_engine,
    expire_on_commit=False,
    autoflush=False,
)


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
