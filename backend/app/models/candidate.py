from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
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


class Candidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A candidate derived from a processed resume document."""

    __tablename__ = "candidates"

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

    source_document: Mapped[Document | None] = relationship(lazy="selectin")
    owner: Mapped[User] = relationship(lazy="selectin")
    applications: Mapped[list[Application]] = relationship(
        back_populates="candidate", lazy="selectin"
    )


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

    candidate: Mapped[Candidate] = relationship(
        back_populates="applications", lazy="selectin"
    )
    job: Mapped[Job] = relationship(lazy="selectin")
