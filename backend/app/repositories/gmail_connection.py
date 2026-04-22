"""Data access for the GmailConnection aggregate.

One row per ``(user_id, gmail_email)``. A user may hold multiple
connections; ``upsert`` keys on both columns so re-authorizing the
same address updates tokens in place while a new address adds a row.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GmailConnection


class GmailConnectionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_by_user(self, user_id: UUID) -> list[GmailConnection]:
        """Return every connection owned by ``user_id``, oldest first."""
        result = await self._db.execute(
            select(GmailConnection)
            .where(GmailConnection.user_id == user_id)
            .order_by(GmailConnection.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_user_and_email(
        self, user_id: UUID, gmail_email: str
    ) -> GmailConnection | None:
        result = await self._db.execute(
            select(GmailConnection).where(
                GmailConnection.user_id == user_id,
                GmailConnection.gmail_email == gmail_email,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_user(
        self, user_id: UUID, connection_id: UUID
    ) -> GmailConnection | None:
        """Owner-scoped lookup. ``None`` if the id doesn't exist *or* belongs
        to a different user — routes translate to 404, which hides
        existence from the wrong owner."""
        result = await self._db.execute(
            select(GmailConnection).where(
                GmailConnection.id == connection_id,
                GmailConnection.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, connection_id: UUID) -> GmailConnection | None:
        """Unscoped lookup — only safe inside the worker, which has no HTTP
        user context. HTTP handlers must use ``get_for_user``."""
        return await self._db.get(GmailConnection, connection_id)

    async def list_all(self) -> list[GmailConnection]:
        """Used by the sync fan-out task to iterate every active connection."""
        result = await self._db.execute(select(GmailConnection))
        return list(result.scalars().all())

    async def upsert(
        self,
        *,
        user_id: UUID,
        gmail_email: str,
        refresh_token: str,
        scopes: list[str],
    ) -> GmailConnection:
        existing = await self.get_by_user_and_email(user_id, gmail_email)
        if existing is not None:
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
