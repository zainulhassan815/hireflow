from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.encryption import EncryptedString
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.job import Job
    from app.models.user import User


class ApplicationStatus(StrEnum):
    NEW = "new"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    INTERVIEWED = "interviewed"
    HIRED = "hired"


class AttachmentRole(StrEnum):
    RESUME = "resume"
    CERTIFICATE = "certificate"
    PORTFOLIO = "portfolio"
    COVER_LETTER = "cover_letter"
    TRANSCRIPT = "transcript"
    OTHER = "other"


# Roles whose extracted skills feed the credential_match scoring signal.
# A resume/cover_letter doesn't count as a credential — those are the
# baseline the credential boost is measured on top of.
CREDENTIAL_ROLES = frozenset(
    {AttachmentRole.CERTIFICATE, AttachmentRole.PORTFOLIO, AttachmentRole.TRANSCRIPT}
)


class Candidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A candidate derived from a processed resume document."""

    __tablename__ = "candidates"
    # Partial unique index: one candidate per (owner, email). NULL
    # emails are exempt so unparseable resumes don't collide.
    __table_args__ = (
        Index(
            "ix_candidates_owner_email_unique",
            "owner_id",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    skills: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    education: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    # Keywords merged from non-resume attachments (portfolio READMEs,
    # case studies). Kept separate from ``skills`` — these are softer
    # signal that should not masquerade as extracted resume skills.
    supplementary_keywords: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )

    # F104.a — one-sentence recruiter brief used as the candidate-
    # summary retrieval anchor (separate Chroma collection, surfaced
    # in RAG context for who/which-person-shaped questions).
    # ``summary_version`` lets the backfill script detect a stale
    # summary after a ``SUMMARY_VERSION`` bump in the
    # ``CandidateSummaryService`` prompt.
    summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ``post_update=True`` mirrors the same flag on the reverse edge
    # (``Document.authored_by``). The ``source_document_id`` →
    # ``Document.id`` direction is the original F41 link; pairing both
    # sides with post_update makes SA defer the FK writes to a
    # separate UPDATE statement after both rows commit, which is the
    # only reliable way to flush a transaction that touches both
    # cycle directions in one session.
    source_document: Mapped[Document | None] = relationship(
        "Document",
        foreign_keys=[source_document_id],
        lazy="selectin",
        post_update=True,
    )
    owner: Mapped[User] = relationship(lazy="selectin")
    applications: Mapped[list[Application]] = relationship(
        back_populates="candidate", lazy="selectin"
    )
    # F103.c — every doc whose ``authored_by_id`` points at this candidate.
    # For resumes this includes the candidate's own ``source_document``;
    # for portfolios / case studies / contracts it surfaces all the
    # writing the candidate did. Distinct from ``source_document`` (which
    # means "the resume this candidate was parsed from") on purpose —
    # callers reading "what did this person write" should reach for
    # ``authored_documents``.
    authored_documents: Mapped[list[Document]] = relationship(
        "Document",
        foreign_keys="Document.authored_by_id",
        back_populates="authored_by",
        lazy="selectin",
    )
    # The bundle of files submitted for this candidate (resume + certs +
    # portfolio + …). The ``role=resume`` row mirrors ``source_document``;
    # the service keeps the two in sync.
    attachments: Mapped[list[CandidateAttachment]] = relationship(
        back_populates="candidate",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="CandidateAttachment.created_at",
    )


class CandidateAttachment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One file attached to a candidate, tagged with the role it plays.

    A candidate is a bundle, not a single resume: the join row carries the
    ``role`` (resume / certificate / portfolio / …) so scoring can weight
    credentials distinctly from the resume. Unique on
    ``(candidate_id, document_id)`` — a file attaches to a candidate once —
    but a single document may attach to several candidates (a shared
    recruiting-event batch cert), so ``document_id`` alone is not unique.
    """

    __tablename__ = "candidate_attachments"
    __table_args__ = (
        Index(
            "ix_candidate_attachments_candidate_document_unique",
            "candidate_id",
            "document_id",
            unique=True,
        ),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[AttachmentRole] = mapped_column(
        SAEnum(
            AttachmentRole,
            name="attachment_role",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    candidate: Mapped[Candidate] = relationship(back_populates="attachments")
    document: Mapped[Document] = relationship(lazy="selectin")


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Links a candidate to a job with a match score and status."""

    __tablename__ = "applications"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(
            ApplicationStatus,
            name="application_status",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=ApplicationStatus.NEW,
        nullable=False,
        index=True,
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Persisted so the list hover popover can render the breakdown
    # without recomputing. Shape matches `MatchBreakdown` in
    # app/schemas/candidate.py; JSONB for forward flexibility.
    match_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    candidate: Mapped[Candidate] = relationship(
        back_populates="applications", lazy="selectin"
    )
    job: Mapped[Job] = relationship(lazy="selectin")
