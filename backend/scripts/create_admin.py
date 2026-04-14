"""Seed (or promote) an admin user.

Reads credentials from env vars:
  ADMIN_EMAIL      (required)
  ADMIN_PASSWORD   (required when creating a new user; ignored when promoting)
  ADMIN_FULL_NAME  (optional, defaults to "Admin")

Idempotent:
  - If no user with ADMIN_EMAIL exists, creates one with role=admin.
  - If one exists, promotes to admin (leaves password alone).

Usage:
    ADMIN_EMAIL=root@hireflow.io ADMIN_PASSWORD=changeme \\
        uv run python scripts/create_admin.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


async def main() -> int:
    os.environ.setdefault("JWT_SECRET_KEY", "a]kP9#mQ$2xR!vN7&wZ5^tL0@dF3+hY8")

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sqlalchemy import select

    from app.adapters.argon2_hasher import Argon2Hasher
    from app.core.db import SessionLocal
    from app.models import User, UserRole

    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    full_name = os.environ.get("ADMIN_FULL_NAME", "Admin")

    if not email:
        print("ADMIN_EMAIL is required", file=sys.stderr)
        return 2

    hasher = Argon2Hasher()

    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()

        if user is None:
            if not password:
                print(
                    "ADMIN_PASSWORD is required when creating a new admin",
                    file=sys.stderr,
                )
                return 2
            user = User(
                email=email.lower(),
                hashed_password=hasher.hash(password),
                full_name=full_name,
                role=UserRole.ADMIN,
            )
            db.add(user)
            await db.commit()
            print(f"created admin: {user.email}")
            return 0

        if user.role == UserRole.ADMIN:
            print(f"already admin: {user.email}")
            return 0

        user.role = UserRole.ADMIN
        await db.commit()
        print(f"promoted to admin: {user.email}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
