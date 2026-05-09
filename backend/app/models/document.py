from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, FetchedValue, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.candidate import Candidate
    from app.models.document_element import DocumentElement
    from app.models.user import User


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DocumentType(StrEnum):
    RESUME = "resume"
    REPORT = "report"
    CONTRACT = "contract"
    LETTER = "letter"
    OTHER = "other"


class AuthorSource(StrEnum):
    """How ``Document.authored_by_id`` got set.

    F103.c's ``AuthorLinkageService`` sets ``email_match`` when an
    email-in-doc matches a candidate's email. F103.c.2's manual
    PATCH route sets ``manual``. Backfill scripts must not
    overwrite ``manual`` links — that's the audit trail's purpose.

    Dangling-source caveat: when a candidate is deleted, the FK
    becomes NULL via ``ON DELETE SET NULL`` but this column stays
    at its prior value. Every reader checks ``authored_by_id IS
    NOT NULL`` first; the dangling value is benign.
    """

    EMAIL_MATCH = "email_match"
    MANUAL = "manual"


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)

    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(
            DocumentStatus,
            name="document_status",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
    )

    document_type: Mapped[DocumentType | None] = mapped_column(
        SAEnum(
            DocumentType,
            name="document_type",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )

    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=None
    )

    # F82.d pipeline versioning. Stamped on each doc at index time so
    # targeted re-indexing can pick only docs whose version differs
    # from the code's current constants.
    extraction_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    chunking_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    embedding_model_version: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )

    # F105.b — canonical viewable-asset descriptor, populated after
    # text extraction by ``ViewerPreparationService``. ``viewable_kind``
    # matches ``ViewableKind`` (one of ``pdf`` / ``image`` / ``table`` /
    # ``text`` / ``unsupported``). ``viewable_key`` is the MinIO key
    # the render path signs (equals ``storage_key`` for passthroughs,
    # a freshly-written ``viewable/<doc_id>.pdf`` for office conversions,
    # NULL for unsupported kinds). Both nullable so pre-F105.b rows
    # stay valid; the render path falls back to ``storage_key`` when
    # unset.
    viewable_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    viewable_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Read-only Postgres-generated weighted tsvector. Populated automatically
    # by the database on insert/update; never written from the ORM. Powers
    # lexical retrieval via ts_rank_cd in the search service.
    #
    # F85 added a single-field version over extracted_text. F87 replaced
    # it with a multi-field weighted version: filename (A) + skills (B) +
    # extracted_text (C). ``ts_rank_cd`` respects the per-field weights so
    # a filename match outranks a body-only mention without ranking-code
    # changes.
    search_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        nullable=True,
        server_default=FetchedValue(),
        server_onupdate=FetchedValue(),
    )

    # F103.c — author linkage. Set by ``AuthorLinkageService`` either at
    # ingestion time (email-in-doc ↔ candidate.email) or via the deferred
    # backfill that runs whenever a candidate is created/updated. NULL
    # for documents whose author can't be inferred (no extractable email,
    # or email not yet matching a candidate). Mutual FK with
    # ``Candidate.source_document_id`` is intentional and reflects the
    # real graph: a candidate references the resume it parsed from, the
    # resume (and any other doc the candidate authored) references back.
    # ON DELETE SET NULL on both edges — no cascade loop.
    authored_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # F103.c.2 — distinguishes operator-set ('manual') from inferred
    # ('email_match') links. Used by AuthorLinkageService and the
    # relink_authors backfill to skip docs whose author was set by
    # hand. May dangle (non-NULL) after a candidate deletion sets
    # ``authored_by_id`` to NULL via ON DELETE SET NULL — readers
    # must check ``authored_by_id IS NOT NULL`` first.
    authored_by_source: Mapped[AuthorSource | None] = mapped_column(
        SAEnum(
            AuthorSource,
            name="documents_authored_by_source",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )

    owner: Mapped[User] = relationship(lazy="selectin")
    # ``post_update=True`` breaks the deliberate FK cycle with
    # ``Candidate.source_document_id`` at flush time. Without it, a
    # transaction that touches both edges (e.g. F103.d's name backfill,
    # which updates a Candidate row whose source_document_id points at
    # this doc, then sets this doc's authored_by_id pointing back) hits
    # a "Circular dependency detected" PendingRollbackError. The
    # ``post_update`` semantic tells SA to issue the FK update as a
    # separate UPDATE after both rows commit, sidestepping the cycle.
    authored_by: Mapped[Candidate | None] = relationship(
        "Candidate",
        foreign_keys=[authored_by_id],
        back_populates="authored_documents",
        lazy="selectin",
        post_update=True,
    )

    elements: Mapped[list[DocumentElement]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentElement.order_index",
        lazy="selectin",
    )
