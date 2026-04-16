"""Activity logging service.

Provides a simple API for recording user actions. Called from routes
and services — not via middleware, to keep logging explicit and
avoid coupling to HTTP request lifecycle.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from app.models import ActivityAction, ActivityLog
from app.repositories.activity_log import ActivityLogRepository

logger = logging.getLogger(__name__)


class ActivityService:
    def __init__(self, logs: ActivityLogRepository) -> None:
        self._logs = logs

    async def log(
        self,
        *,
        actor_id: UUID | None,
        action: ActivityAction,
        resource_type: str | None = None,
        resource_id: str | None = None,
        detail: str | None = None,
        ip_address: str | None = None,
    ) -> ActivityLog:
        entry = await self._logs.create(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            ip_address=ip_address,
        )
        logger.info(
            "activity: %s by %s on %s/%s",
            action,
            actor_id,
            resource_type,
            resource_id,
        )
        return entry

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
        return await self._logs.list_logs(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
