"""Job posting management."""

from __future__ import annotations

from uuid import UUID

from app.domain.exceptions import Forbidden, NotFound
from app.models import Job, JobStatus, User, UserRole
from app.repositories.job import JobRepository


class JobService:
    def __init__(self, jobs: JobRepository) -> None:
        self._jobs = jobs

    async def create(self, *, owner: User, **kwargs) -> Job:
        return await self._jobs.create(owner_id=owner.id, **kwargs)

    async def get(self, job_id: UUID, *, actor: User) -> Job:
        job = await self._jobs.get(job_id)
        if job is None:
            raise NotFound("Job not found.")
        self._ensure_access(job, actor)
        return job

    async def update(self, job_id: UUID, *, actor: User, **updates) -> Job:
        job = await self.get(job_id, actor=actor)
        for key, value in updates.items():
            if value is not None:
                setattr(job, key, value)
        return await self._jobs.save(job)

    async def delete(self, job_id: UUID, *, actor: User) -> None:
        job = await self.get(job_id, actor=actor)
        await self._jobs.delete(job)

    async def list_for_user(
        self,
        owner_id: UUID,
        *,
        status: JobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        return await self._jobs.list_by_owner(
            owner_id, status=status, limit=limit, offset=offset
        )

    @staticmethod
    def _ensure_access(job: Job, actor: User) -> None:
        if actor.role == UserRole.ADMIN:
            return
        if job.owner_id != actor.id:
            raise Forbidden("You do not have access to this job.")
