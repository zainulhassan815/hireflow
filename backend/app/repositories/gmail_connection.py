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

    async def list_all(self, *, include_needs_reauth: bool) -> list[GmailConnection]:
        """Connections for the sync fan-out.

        ``include_needs_reauth`` is required rather than defaulted: a
        connection whose token Google already rejected fails on every
        tick, so the scheduler must opt in deliberately to see it.
        """
        stmt = select(GmailConnection)
        if not include_needs_reauth:
            stmt = stmt.where(GmailConnection.reauth_required_at.is_(None))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def mark_needs_reauth(self, conn: GmailConnection) -> None:
        """Flag a dead refresh token without destroying the connection.

        Deleting the row would cascade the ingest ledger away, and the
        next reconnect would re-import every message as new.
        """
        conn.reauth_required_at = datetime.now(UTC)
        await self._db.commit()

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
            # Reconnecting is what clears the flag; the row, its ledger
            # and its settings carry straight on from where they stopped.
            existing.reauth_required_at = None
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

    async def start_backfill(
        self, conn: GmailConnection, *, before: datetime, until: datetime
    ) -> None:
        conn.backfill_before = before
        conn.backfill_until = until
        await self._db.commit()

    async def advance_backfill(self, conn: GmailConnection, before: datetime) -> None:
        conn.backfill_before = before
        await self._db.commit()

    async def set_history_id(
        self, conn: GmailConnection, history_id: str | None
    ) -> None:
        conn.last_history_id = history_id
        await self._db.commit()

    async def set_mirror_deletions(self, conn: GmailConnection, enabled: bool) -> None:
        conn.mirror_deletions = enabled
        await self._db.commit()

    async def finish_backfill(self, conn: GmailConnection) -> None:
        conn.backfill_before = None
        conn.backfill_until = None
        await self._db.commit()
