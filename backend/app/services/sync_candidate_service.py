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

logger = logging.getLogger(__name__)


class SyncCandidateService:
    def __init__(self, session: Session) -> None:
        self._session = session

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
        existing = self._session.execute(
            select(Candidate).where(Candidate.source_document_id == document.id)
        ).scalar_one_or_none()

        meta = document.metadata_ or {}
        name = meta.get("name")
        email = _first(meta.get("emails"))
        phone = _first(meta.get("phones"))
        skills = meta.get("skills", []) or []
        experience_years = meta.get("experience_years")
        education = meta.get("education")

        if existing is not None:
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
        return candidate


def _first(value: object) -> str | None:
    if isinstance(value, list) and value:
        first = value[0]
        return first if isinstance(first, str) else None
    return None


__all__ = ["SyncCandidateService"]
