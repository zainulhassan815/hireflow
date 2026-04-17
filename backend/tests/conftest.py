"""Test harness for the backend.

Design decisions (see docs/dev/F71-tests/):

* **Real Postgres, real Redis.** Tests run against the same containers
  that ``make dev`` uses — a dedicated database (``hr_screening_test``)
  and Redis index (``15``). No SQLite, no ``fakeredis``.
* **HTTP mocks only at the Google boundary.** Everything else runs for
  real: services, repositories, JWT issuance, blob storage.
* **Truncate between tests.** Schema survives across the session so
  Alembic runs once. ``Base.metadata.sorted_tables`` drives TRUNCATE —
  no hand-maintained table list.
* **Settings swap happens in ``pytest_configure``.** Before any test
  module imports anything from ``app.*``, environment variables point
  at the test DB / Redis index.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest

# --------------------------------------------------------------------------
# pytest_configure: runs before test modules are imported.
# This is the one safe place to mutate env vars that `app.core.config`
# reads at import time.
# --------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Point the app at the test DB + Redis index before any import of `app.*`."""
    dev_env = _read_env_file(Path(__file__).parent.parent / ".env")

    dev_db = dev_env.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/hr_screening",
    )
    test_db = _swap_db_name(dev_db, "hr_screening_test")

    dev_redis = dev_env.get("REDIS_URL", "redis://localhost:6379/0")
    test_redis = _swap_redis_db(dev_redis, 15)

    os.environ["DATABASE_URL"] = test_db
    os.environ["REDIS_URL"] = test_redis
    # Dev `.env` often has DEBUG=true which turns on SQLAlchemy echo;
    # tests don't need the SQL trace and it swamps failure output.
    os.environ["DEBUG"] = "false"

    # Fill required-but-missing secrets with deterministic test values.
    # Real secrets (if any) from `.env` stay untouched so a developer
    # with a working dev env doesn't have to duplicate Gmail credentials.
    _default_env(dev_env, "JWT_SECRET_KEY", "a" * 64)
    _default_env(
        dev_env,
        "ENCRYPTION_KEYS",
        # A deterministic Fernet key for tests. Safe to check in — it
        # never encrypts real data.
        "dGVzdC1rZXktZm9yLWhpcmVmbG93LXVuaXR0ZXN0cy0wMDAwMA==",
    )


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _swap_db_name(url: str, new_name: str) -> str:
    """Replace the database name at the end of a SQLAlchemy URL."""
    if "/" not in url:
        return url
    base, _, _ = url.rpartition("/")
    return f"{base}/{new_name}"


def _swap_redis_db(url: str, new_index: int) -> str:
    if "/" not in url.split("://", 1)[-1]:
        return f"{url}/{new_index}"
    base, _, _ = url.rpartition("/")
    return f"{base}/{new_index}"


def _default_env(dev_env: dict[str, str], key: str, fallback: str) -> None:
    """Populate an env var from dev `.env` if present, else a test default."""
    if key in os.environ:
        return
    os.environ[key] = dev_env.get(key) or fallback


# --------------------------------------------------------------------------
# Imports from `app.*` only happen AFTER pytest_configure has run.
# Placed inside fixtures so the env-var dance above settles first.
# --------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def prepare_test_database() -> Iterator[None]:
    """Create the test DB if missing, run Alembic to head, then keep it around.

    Dropping between sessions isn't worth it — schema churn is rare and
    per-test TRUNCATE gives isolation.
    """
    import asyncio

    asyncio.run(_create_test_database_if_missing())

    import subprocess

    backend_dir = Path(__file__).parent.parent
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        check=True,
        env={**os.environ},
    )
    yield


async def _create_test_database_if_missing() -> None:
    """Postgres has no ``CREATE DATABASE IF NOT EXISTS``; this is the manual check."""
    import asyncpg

    from app.core.config import settings

    test_db_url = settings.database_url
    target_db = test_db_url.rsplit("/", 1)[-1]
    admin_url = test_db_url.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres"

    conn = await asyncpg.connect(admin_url)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", target_db
        )
        if not exists:
            # CREATE DATABASE can't run in a transaction block; asyncpg
            # doesn't wrap it in one for a bare `execute`.
            await conn.execute(f'CREATE DATABASE "{target_db}"')
    finally:
        await conn.close()


# --------------------------------------------------------------------------
# Per-test isolation
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    """TRUNCATE every app table before each test.

    ``sorted_tables`` gives FK-safe order; ``CASCADE`` is belt-and-braces
    in case a model adds a self-referential relationship later.
    """
    from sqlalchemy import text

    from app.core.db import SessionLocal
    from app.models import Base

    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)

    async with SessionLocal() as session:
        await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await session.commit()

    yield


@pytest.fixture(autouse=True)
async def clean_redis() -> AsyncIterator[None]:
    """FLUSHDB on index 15 before each test."""
    from app.core.redis import redis_client

    await redis_client.flushdb()
    yield


# --------------------------------------------------------------------------
# Stubs: Celery `.delay()` → recorder
# --------------------------------------------------------------------------


class EnqueuedTasks:
    """Records which Celery tasks were `.delay()`-ed during a test.

    Use as a list-like object for assertions:

        assert enqueued_tasks.for_task("extract_document_text") == [str(doc.id)]
    """

    def __init__(self) -> None:
        self._calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def record(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self._calls.append((name, args, kwargs))

    @property
    def calls(self) -> list[tuple[str, tuple[Any, ...], dict[str, Any]]]:
        return list(self._calls)

    def for_task(self, name: str) -> list[tuple[Any, ...]]:
        return [args for task_name, args, _ in self._calls if task_name == name]

    def __len__(self) -> int:
        return len(self._calls)


@pytest.fixture(autouse=True)
def enqueued_tasks(monkeypatch: pytest.MonkeyPatch) -> EnqueuedTasks:
    """Replace every Celery ``.delay()`` with a recorder.

    Auto-applied so tests that don't care about Celery don't
    accidentally enqueue real tasks.
    """
    from app.worker import tasks as worker_tasks

    recorder = EnqueuedTasks()

    def _fake_delay(task_name: str):
        def delay(*args: Any, **kwargs: Any) -> None:
            recorder.record(task_name, args, kwargs)

        return delay

    for attr in (
        "extract_document_text",
        "sync_gmail_connection",
        "sync_all_gmail_connections",
    ):
        original = getattr(worker_tasks, attr)
        monkeypatch.setattr(original, "delay", _fake_delay(attr))

    return recorder


# --------------------------------------------------------------------------
# HTTP client
# --------------------------------------------------------------------------


@pytest.fixture
async def client() -> AsyncIterator[Any]:
    """An ``httpx.AsyncClient`` bound to the FastAPI app via ASGI.

    No network traffic; requests go straight into the app. This is the
    fixture most tests depend on.
    """
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client


# --------------------------------------------------------------------------
# User + token fixtures (driven through the real auth service)
# --------------------------------------------------------------------------


@pytest.fixture
async def admin_user() -> Any:
    """Seed an admin user directly via the repository.

    Tests that want to log in as admin should use ``admin_token`` which
    depends on this fixture.
    """
    from app.adapters.argon2_hasher import Argon2Hasher
    from app.core.db import SessionLocal
    from app.models import UserRole
    from app.repositories.user import UserRepository

    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.create(
            email="admin@test.hireflow.io",
            hashed_password=Argon2Hasher().hash("admin-test-password"),
            full_name="Test Admin",
            role=UserRole.ADMIN,
        )
        return user


@pytest.fixture
async def hr_user() -> Any:
    """Seed a regular HR-role user."""
    from app.adapters.argon2_hasher import Argon2Hasher
    from app.core.db import SessionLocal
    from app.models import UserRole
    from app.repositories.user import UserRepository

    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.create(
            email="hr@test.hireflow.io",
            hashed_password=Argon2Hasher().hash("hr-test-password"),
            full_name="Test HR",
            role=UserRole.HR,
        )
        return user


@pytest.fixture
async def admin_token(client: Any, admin_user: Any) -> str:
    """Log in the admin user through the real ``/auth/login`` endpoint."""
    response = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.hireflow.io", "password": "admin-test-password"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
async def hr_token(client: Any, hr_user: Any) -> str:
    response = await client.post(
        "/api/auth/login",
        json={"email": "hr@test.hireflow.io", "password": "hr-test-password"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def auth_headers():
    """Build an ``Authorization`` header dict from a token."""

    def _build(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return _build
