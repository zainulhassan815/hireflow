"""Candidate management and auto-creation from processed documents."""

from __future__ import annotations

import logging
from uuid import UUID

from app.domain.exceptions import Forbidden, NotFound, ResumeAlreadyAttached
from app.models import (
    Application,
    ApplicationStatus,
    AttachmentRole,
    Candidate,
    CandidateAttachment,
    Document,
    User,
    UserRole,
)
from app.models.candidate import CREDENTIAL_ROLES
from app.repositories.candidate import ApplicationRepository, CandidateRepository
from app.repositories.job import JobRepository

logger = logging.getLogger(__name__)


class CandidateService:
    def __init__(
        self,
        candidates: CandidateRepository,
        applications: ApplicationRepository,
        jobs: JobRepository,
    ) -> None:
        self._candidates = candidates
        self._applications = applications
        self._jobs = jobs

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

    async def list_attachments(
        self, candidate_id: UUID, *, actor: User
    ) -> list[CandidateAttachment]:
        candidate = await self.get(candidate_id, actor=actor)
        return await self._candidates.list_attachments(candidate.id)

    async def add_attachments(
        self,
        candidate_id: UUID,
        items: list[tuple[Document, AttachmentRole]],
        *,
        actor: User,
    ) -> list[CandidateAttachment]:
        """Attach documents to a candidate atomically.

        A candidate holds at most one ``role=resume`` attachment — a second
        one (already present, or two in the same batch) is a 409. Attaching
        a resume also repoints ``source_document_id`` so the pointer and the
        join table stay in sync. Documents already attached are skipped
        (idempotent). Credential-bearing files merge their skills into the
        candidate profile on the way in.
        """
        candidate = await self.get(candidate_id, actor=actor)
        existing = await self._candidates.list_attachments(candidate.id)
        existing_doc_ids = {a.document_id for a in existing}
        has_resume = any(a.role == AttachmentRole.RESUME for a in existing)

        incoming_resumes = sum(1 for _, role in items if role == AttachmentRole.RESUME)
        if incoming_resumes > 1 or (incoming_resumes == 1 and has_resume):
            raise ResumeAlreadyAttached(
                "This candidate already has a resume. Detach it before "
                "attaching a new one."
            )

        to_add: list[tuple[UUID, AttachmentRole]] = []
        resume_doc_id: UUID | None = None
        seen: set[UUID] = set()
        for document, role in items:
            if document.id in existing_doc_ids or document.id in seen:
                continue
            seen.add(document.id)
            to_add.append((document.id, role))
            if role == AttachmentRole.RESUME:
                resume_doc_id = document.id
            self._merge_attachment_signals(candidate, document, role)

        if resume_doc_id is not None:
            candidate.source_document_id = resume_doc_id

        return await self._candidates.add_attachments(candidate, to_add)

    async def remove_attachment(
        self, candidate_id: UUID, document_id: UUID, *, actor: User
    ) -> None:
        """Detach a document from a candidate. The underlying Document is
        left intact (it keeps its own ownership per F22). Detaching the
        resume clears the ``source_document_id`` pointer."""
        candidate = await self.get(candidate_id, actor=actor)
        attachment = await self._candidates.get_attachment(candidate.id, document_id)
        if attachment is None:
            raise NotFound("Attachment not found.")
        if (
            attachment.role == AttachmentRole.RESUME
            and candidate.source_document_id == document_id
        ):
            candidate.source_document_id = None
        await self._candidates.delete_attachment(attachment)

    def _merge_attachment_signals(
        self, candidate: Candidate, document: Document, role: AttachmentRole
    ) -> None:
        """Union credential-bearing skills / keywords into the candidate.

        Idempotent (set union). Only credential roles enrich the profile —
        the resume stays the source of truth for name / email / experience.
        """
        if role not in CREDENTIAL_ROLES:
            return
        meta = document.metadata_ or {}
        doc_skills = meta.get("skills") or []
        if doc_skills:
            candidate.skills = sorted(set(candidate.skills) | set(doc_skills))
        if role == AttachmentRole.PORTFOLIO:
            keywords = meta.get("keywords") or []
            if keywords:
                candidate.supplementary_keywords = sorted(
                    set(candidate.supplementary_keywords or []) | set(keywords)
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
        # Caller must own the parent job (admins bypass). Application
        # auto-loads ``job`` via ``lazy="selectin"`` so this costs no
        # extra round-trip. 403 (not 404) matches the cross-tenant
        # convention used by Document/Candidate/Job services.
        self._ensure_job_access(app.job, actor)
        app.status = status
        return await self._applications.save(app)

    async def bulk_update_application_status(
        self,
        application_ids: list[UUID],
        status: ApplicationStatus,
        *,
        actor: User,
    ) -> list[Application]:
        """Apply ``status`` to a batch of applications atomically.

        All-or-nothing: if any application is missing or owned by a
        different user, the whole batch rejects (404 / 403). Frontend
        only selects from rows the caller can already see, so a cross-
        tenant id in the batch is an attack surface, not a valid UX
        path — fail loud rather than silently skip.

        Dedup is handled by passing ids through a set; the response
        preserves the input order so the frontend can map back easily.
        """
        if not application_ids:
            return []

        unique_ids = list(dict.fromkeys(application_ids))
        apps = await self._applications.list_by_ids(unique_ids)
        if len(apps) != len(unique_ids):
            raise NotFound("One or more applications not found.")

        # Authorize every parent job. Checking here (before any write)
        # means a 403 doesn't leave a partial mutation behind.
        for app in apps:
            self._ensure_job_access(app.job, actor)

        for app in apps:
            app.status = status
        return await self._applications.save_many(apps)

    async def list_applications_for_job(
        self,
        job_id: UUID,
        *,
        actor: User,
        status: ApplicationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Application]:
        # Authorize by fetching the parent job first. Missing job ⇒
        # 404 (no applications to leak); wrong owner ⇒ 403.
        job = await self._jobs.get(job_id)
        if job is None:
            raise NotFound("Job not found.")
        self._ensure_job_access(job, actor)
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

    @staticmethod
    def _ensure_job_access(job, actor: User) -> None:
        """Applications inherit their parent job's ownership.

        Kept local (not calling ``JobService._ensure_access``) to avoid
        a service-to-service import; the policy is trivial and unlikely
        to diverge. If it ever grows (e.g. team-shared jobs), move
        both into ``app/services/authz.py`` as a shared helper.
        """
        if actor.role == UserRole.ADMIN:
            return
        if job.owner_id != actor.id:
            raise Forbidden("You do not have access to this application.")


def _first(lst: list | None) -> str | None:
    if lst and len(lst) > 0:
        return lst[0]
    return None
