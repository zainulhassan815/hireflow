"""Data access for Candidate and Application aggregates."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, ApplicationStatus, Candidate


class CandidateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, candidate_id: UUID) -> Candidate | None:
        return await self._db.get(Candidate, candidate_id)

    async def get_by_document(self, document_id: UUID) -> Candidate | None:
        result = await self._db.execute(
            select(Candidate).where(Candidate.source_document_id == document_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Candidate:
        candidate = Candidate(**kwargs)
        self._db.add(candidate)
        await self._db.commit()
        await self._db.refresh(candidate)
        return candidate

    async def save(self, candidate: Candidate) -> Candidate:
        await self._db.commit()
        await self._db.refresh(candidate)
        return candidate

    async def list_by_owner(
        self, owner_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Candidate]:
        result = await self._db.execute(
            select(Candidate)
            .where(Candidate.owner_id == owner_id)
            .order_by(Candidate.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())


class ApplicationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, application_id: UUID) -> Application | None:
        return await self._db.get(Application, application_id)

    async def create(self, **kwargs) -> Application:
        app = Application(**kwargs)
        self._db.add(app)
        await self._db.commit()
        await self._db.refresh(app)
        return app

    async def save(self, app: Application) -> Application:
        await self._db.commit()
        await self._db.refresh(app)
        return app

    async def get_for_job_and_candidate(
        self, job_id: UUID, candidate_id: UUID
    ) -> Application | None:
        result = await self._db.execute(
            select(Application).where(
                Application.job_id == job_id,
                Application.candidate_id == candidate_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_job(
        self,
        job_id: UUID,
        *,
        status: ApplicationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Application]:
        stmt = (
            select(Application)
            .where(Application.job_id == job_id)
            .order_by(Application.score.desc().nullslast())
        )
        if status is not None:
            stmt = stmt.where(Application.status == status)
        stmt = stmt.limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
