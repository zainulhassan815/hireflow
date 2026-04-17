"""Data access for the Gmail ingest ledger.

Two operations carry the weight of the sync worker's correctness:

* ``reset_stale_claims`` sweeps rows that a prior worker left in the
  ``claimed`` state past the visibility timeout, moving them to
  ``reset`` so the next claim can re-run them.
* ``claim_or_skip`` is the atomic "is this a new message?" check. It
  either returns a freshly-claimed row or ``None`` if another worker
  already handled it.

Everything else is plain CRUD.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GmailIngestedMessage, GmailIngestStatus


class GmailIngestedMessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def reset_stale_claims(
        self, connection_id: UUID, *, timeout_minutes: int
    ) -> int:
        """Move ``claimed`` rows older than the timeout back to ``reset``.

        Returns the number of rows reset. Running this at the start of
        every sync tick keeps crashed-mid-ingest messages from being
        permanently stuck.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=timeout_minutes)
        result = await self._db.execute(
            update(GmailIngestedMessage)
            .where(
                and_(
                    GmailIngestedMessage.connection_id == connection_id,
                    GmailIngestedMessage.ingest_status == GmailIngestStatus.CLAIMED,
                    GmailIngestedMessage.updated_at < cutoff,
                )
            )
            .values(
                ingest_status=GmailIngestStatus.RESET,
                updated_at=datetime.now(UTC),
            )
        )
        await self._db.commit()
        return result.rowcount or 0

    async def claim_or_skip(
        self, connection_id: UUID, gmail_message_id: str
    ) -> GmailIngestedMessage | None:
        """Try to claim a message. Return the row if newly claimed, else ``None``.

        Encodes the full claim-or-reset state machine in one SQL statement:

        * If no row exists → insert with ``ingest_status='claimed'`` and
          return it.
        * If a row exists with ``ingest_status='reset'`` → flip it back to
          ``claimed``, bump ``updated_at``, and return it.
        * Otherwise (``completed``, ``failed``, or another worker's
          in-flight ``claimed``) → do nothing, return ``None``.

        The ``RETURNING`` clause yields the row only when the INSERT or
        UPDATE fired, which is exactly the "newly claimed" case.
        """
        stmt = pg_insert(GmailIngestedMessage).values(
            connection_id=connection_id,
            gmail_message_id=gmail_message_id,
            ingest_status=GmailIngestStatus.CLAIMED,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_gmail_ingested_connection_message",
            set_={
                "ingest_status": GmailIngestStatus.CLAIMED,
                "updated_at": datetime.now(UTC),
            },
            where=(GmailIngestedMessage.ingest_status == GmailIngestStatus.RESET),
        ).returning(GmailIngestedMessage)

        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()
        await self._db.commit()
        return row

    async def mark_completed(
        self,
        claim: GmailIngestedMessage,
        *,
        attachment_count: int,
        document_ids: list[UUID],
    ) -> GmailIngestedMessage:
        claim.ingest_status = GmailIngestStatus.COMPLETED
        claim.attachment_count = attachment_count
        claim.document_ids = document_ids
        claim.completed_at = datetime.now(UTC)
        await self._db.commit()
        await self._db.refresh(claim)
        return claim

    async def mark_failed(
        self, claim: GmailIngestedMessage, *, reason: str
    ) -> GmailIngestedMessage:
        # Truncate to 4 KB so one pathological stack trace can't bloat
        # the audit table.
        claim.ingest_status = GmailIngestStatus.FAILED
        claim.failure_reason = reason[:4096]
        claim.completed_at = datetime.now(UTC)
        await self._db.commit()
        await self._db.refresh(claim)
        return claim

    async def get(self, row_id: UUID) -> GmailIngestedMessage | None:
        return await self._db.get(GmailIngestedMessage, row_id)

    async def list_recent(
        self, connection_id: UUID, *, limit: int = 50
    ) -> list[GmailIngestedMessage]:
        result = await self._db.execute(
            select(GmailIngestedMessage)
            .where(GmailIngestedMessage.connection_id == connection_id)
            .order_by(GmailIngestedMessage.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
