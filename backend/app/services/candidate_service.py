"""Candidate management and auto-creation from processed documents."""

from __future__ import annotations

import logging
from uuid import UUID

from app.domain.exceptions import Forbidden, NotFound
from app.models import (
    Application,
    ApplicationStatus,
    Candidate,
    Document,
    User,
    UserRole,
)
from app.repositories.candidate import ApplicationRepository, CandidateRepository

logger = logging.getLogger(__name__)


class CandidateService:
    def __init__(
        self,
        candidates: CandidateRepository,
        applications: ApplicationRepository,
    ) -> None:
        self._candidates = candidates
        self._applications = applications

    async def create_from_document(
        self, document: Document, *, owner: User
    ) -> Candidate:
        """Create or update a candidate from a processed resume document."""
        existing = await self._candidates.get_by_document(document.id)
        if existing is not None:
            return await self._update_from_metadata(existing, document)

        meta = document.metadata_ or {}
        candidate = await self._candidates.create(
            owner_id=owner.id,
            source_document_id=document.id,
            name=meta.get("name"),
            email=_first(meta.get("emails")),
            phone=_first(meta.get("phones")),
            skills=meta.get("skills", []),
            experience_years=meta.get("experience_years"),
            education=meta.get("education"),
        )
        logger.info("created candidate %s from document %s", candidate.id, document.id)
        return candidate

    async def get(self, candidate_id: UUID, *, actor: User) -> Candidate:
        candidate = await self._candidates.get(candidate_id)
        if candidate is None:
            raise NotFound("Candidate not found.")
        self._ensure_access(candidate, actor)
        return candidate

    async def list_for_user(
        self, owner_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Candidate]:
        return await self._candidates.list_by_owner(
            owner_id, limit=limit, offset=offset
        )

    async def apply_to_job(
        self,
        candidate_id: UUID,
        job_id: UUID,
        *,
        actor: User,
        score: float | None = None,
    ) -> Application:
        candidate = await self.get(candidate_id, actor=actor)
        existing = await self._applications.get_for_job_and_candidate(
            job_id, candidate.id
        )
        if existing is not None:
            if score is not None:
                existing.score = score
                return await self._applications.save(existing)
            return existing

        return await self._applications.create(
            candidate_id=candidate.id,
            job_id=job_id,
            score=score,
        )

    async def update_application_status(
        self,
        application_id: UUID,
        status: ApplicationStatus,
        *,
        actor: User,
    ) -> Application:
        app = await self._applications.get(application_id)
        if app is None:
            raise NotFound("Application not found.")
        app.status = status
        return await self._applications.save(app)

    async def list_applications_for_job(
        self,
        job_id: UUID,
        *,
        status: ApplicationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Application]:
        return await self._applications.list_by_job(
            job_id, status=status, limit=limit, offset=offset
        )

    async def _update_from_metadata(
        self, candidate: Candidate, document: Document
    ) -> Candidate:
        meta = document.metadata_ or {}
        candidate.name = meta.get("name") or candidate.name
        candidate.email = _first(meta.get("emails")) or candidate.email
        candidate.phone = _first(meta.get("phones")) or candidate.phone
        candidate.skills = meta.get("skills", candidate.skills)
        candidate.experience_years = meta.get(
            "experience_years", candidate.experience_years
        )
        candidate.education = meta.get("education", candidate.education)
        return await self._candidates.save(candidate)

    @staticmethod
    def _ensure_access(candidate: Candidate, actor: User) -> None:
        if actor.role == UserRole.ADMIN:
            return
        if candidate.owner_id != actor.id:
            raise Forbidden("You do not have access to this candidate.")


def _first(lst: list | None) -> str | None:
    if lst and len(lst) > 0:
        return lst[0]
    return None
