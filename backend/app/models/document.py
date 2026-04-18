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

    # Read-only Postgres-generated tsvector over extracted_text. Populated
    # automatically by the database on insert/update; never written from the
    # ORM. Powers F85 lexical retrieval via ts_rank_cd in the search service.
    extracted_text_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        nullable=True,
        server_default=FetchedValue(),
        server_onupdate=FetchedValue(),
    )

    owner: Mapped[User] = relationship(lazy="selectin")
