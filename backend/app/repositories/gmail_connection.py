"""Data access for the GmailConnection aggregate."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GmailConnection


class GmailConnectionRepository:
    """One row per user. ``upsert`` replaces any existing connection atomically."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_user(self, user_id: UUID) -> GmailConnection | None:
        result = await self._db.execute(
            select(GmailConnection).where(GmailConnection.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        user_id: UUID,
        gmail_email: str,
        refresh_token: str,
        scopes: list[str],
    ) -> GmailConnection:
        existing = await self.get_by_user(user_id)
        if existing is not None:
            existing.gmail_email = gmail_email
            existing.refresh_token = refresh_token
            existing.scopes = scopes
            conn = existing
        else:
            conn = GmailConnection(
                user_id=user_id,
                gmail_email=gmail_email,
                refresh_token=refresh_token,
                scopes=scopes,
            )
            self._db.add(conn)
        await self._db.commit()
        await self._db.refresh(conn)
        return conn

    async def delete(self, conn: GmailConnection) -> None:
        await self._db.delete(conn)
        await self._db.commit()

    async def touch_sync(self, conn: GmailConnection) -> None:
        conn.last_synced_at = datetime.now(UTC)
        await self._db.commit()
