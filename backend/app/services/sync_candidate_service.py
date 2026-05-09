"""Synchronous candidate auto-creation for the worker pipeline.

Mirrors the subset of ``CandidateService.create_from_document`` that
the Celery-side extraction pipeline needs, against a sync ``Session``.

Runs at the tail of ``extract_document_text``: when classification
sets ``document_type = RESUME``, we create or update a ``Candidate``
using the metadata the classifier extracted.

Idempotent: the candidate row's ``source_document_id`` has a
unique constraint, so re-processing a document updates rather than
duplicates.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Candidate, Document, DocumentType
from app.services.author_linkage_service import AuthorLinkageService
from app.services.candidate_summary_service import CandidateSummaryService

logger = logging.getLogger(__name__)


class SyncCandidateService:
    def __init__(
        self,
        session: Session,
        *,
        llm_call: object | None = None,
        candidate_embedder: object | None = None,
        candidate_store: object | None = None,
    ) -> None:
        self._session = session
        # F103.c — owns the deferred-resolution path. When a candidate
        # is created or its email changes, scan unlinked docs that
        # already mention this email and backfill the FK.
        self._author_linkage = AuthorLinkageService(session)
        # F104.a — when present, generate a one-line recruiter brief
        # and stamp it on the candidate row at creation/update time.
        # ``None`` keeps the legacy/test path working when the LLM
        # provider isn't wired (e.g., unit tests). The embedder + store
        # are also optional — when set, the summary text is also
        # indexed in the candidate-similarity Chroma collection.
        self._summary: CandidateSummaryService | None = None
        if llm_call is not None:
            self._summary = CandidateSummaryService(
                session,
                llm_call,  # type: ignore[arg-type]
                embedder=candidate_embedder,  # type: ignore[arg-type]
                store=candidate_store,  # type: ignore[arg-type]
            )

    def handle_document_ready(self, document: Document) -> None:
        """Callback hook invoked by ``ExtractionService`` after a document
        reaches ``READY`` status.

        Only acts on resumes. Never raises — candidate creation must
        not roll back extraction's success.
        """
        if document.document_type != DocumentType.RESUME:
            return
        try:
            self._create_or_update(document)
        except Exception:
            logger.exception(
                "auto-candidate creation failed for document %s", document.id
            )

    def _create_or_update(self, document: Document) -> Candidate:
        meta = document.metadata_ or {}
        name = meta.get("name")
        email = _first(meta.get("emails"))
        phone = _first(meta.get("phones"))
        skills = meta.get("skills", []) or []
        experience_years = meta.get("experience_years")
        education = meta.get("education")

        # Dedup priority:
        #   1. Same document reprocessed → match on source_document_id.
        #   2. Different document, same person → match on (owner, email)
        #      when the parser produced an email. Point the existing
        #      candidate at the newest source document so downstream
        #      views (similar docs, search citations) always resolve to
        #      the latest resume.
        existing = self._session.execute(
            select(Candidate).where(Candidate.source_document_id == document.id)
        ).scalar_one_or_none()
        if existing is None and email is not None:
            existing = self._session.execute(
                select(Candidate).where(
                    Candidate.owner_id == document.owner_id,
                    Candidate.email == email,
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.source_document_id = document.id

        if existing is not None:
            email_changed = bool(email) and existing.email != email
            existing.name = name or existing.name
            existing.email = email or existing.email
            existing.phone = phone or existing.phone
            if skills:
                existing.skills = skills
            if experience_years is not None:
                existing.experience_years = experience_years
            if education is not None:
                existing.education = education
            self._session.commit()
            self._session.refresh(existing)
            logger.info(
                "updated candidate %s from document %s",
                existing.id,
                document.id,
            )
            # F103.c — only re-scan unlinked docs when the email
            # actually changed; otherwise the existing FKs still apply
            # and a no-op scan is wasted work.
            if email_changed:
                self._author_linkage.backfill_for_candidate(existing)
            # F104.a — refresh the summary on each resume update so the
            # one-liner reflects the latest skills / education / years.
            # Worker swallows LLM failures internally; safe to call
            # unconditionally.
            if self._summary is not None:
                self._summary.generate_for(
                    existing, resume_text=document.extracted_text
                )
            return existing

        candidate = Candidate(
            owner_id=document.owner_id,
            source_document_id=document.id,
            name=name,
            email=email,
            phone=phone,
            skills=skills,
            experience_years=experience_years,
            education=education,
        )
        self._session.add(candidate)
        self._session.commit()
        self._session.refresh(candidate)
        logger.info(
            "auto-created candidate %s from resume %s", candidate.id, document.id
        )
        # F103.c — fresh candidate may unlock prior portfolio docs
        # uploaded before this candidate's resume.
        self._author_linkage.backfill_for_candidate(candidate)
        # F104.a — generate the recruiter brief now that the candidate
        # row is stable. Worker swallows LLM failures internally.
        if self._summary is not None:
            self._summary.generate_for(candidate, resume_text=document.extracted_text)
        return candidate


def _first(value: object) -> str | None:
    if isinstance(value, list) and value:
        first = value[0]
        return first if isinstance(first, str) else None
    return None


__all__ = ["SyncCandidateService"]
