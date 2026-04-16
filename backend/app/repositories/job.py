"""Data access for the Job aggregate."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobStatus


class JobRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, job_id: UUID) -> Job | None:
        return await self._db.get(Job, job_id)

    async def create(self, **kwargs) -> Job:
        job = Job(**kwargs)
        self._db.add(job)
        await self._db.commit()
        await self._db.refresh(job)
        return job

    async def save(self, job: Job) -> Job:
        await self._db.commit()
        await self._db.refresh(job)
        return job

    async def delete(self, job: Job) -> None:
        await self._db.delete(job)
        await self._db.commit()

    async def list_by_owner(
        self,
        owner_id: UUID,
        *,
        status: JobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        stmt = (
            select(Job).where(Job.owner_id == owner_id).order_by(Job.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(Job.status == status)
        stmt = stmt.limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self,
        *,
        status: JobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        stmt = select(Job).order_by(Job.created_at.desc())
        if status is not None:
            stmt = stmt.where(Job.status == status)
        stmt = stmt.limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
