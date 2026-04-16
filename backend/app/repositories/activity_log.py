"""Data access for activity logs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityAction, ActivityLog


class ActivityLogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, **kwargs) -> ActivityLog:
        log = ActivityLog(**kwargs)
        self._db.add(log)
        await self._db.commit()
        return log

    async def list_logs(
        self,
        *,
        actor_id: UUID | None = None,
        action: ActivityAction | None = None,
        resource_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLog]:
        stmt = select(ActivityLog).order_by(ActivityLog.created_at.desc())

        if actor_id is not None:
            stmt = stmt.where(ActivityLog.actor_id == actor_id)
        if action is not None:
            stmt = stmt.where(ActivityLog.action == action)
        if resource_type is not None:
            stmt = stmt.where(ActivityLog.resource_type == resource_type)
        if date_from is not None:
            stmt = stmt.where(ActivityLog.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(ActivityLog.created_at <= date_to)

        stmt = stmt.limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
