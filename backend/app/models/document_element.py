"""Typed elements of a document from layout-aware extraction (F82.d).

One row per element (``Title``, ``NarrativeText``, ``ListItem``,
``Table``, ...). Persisting these lets re-chunking skip the slow
extraction step; it also keeps the structured output available for
future uses (section-aware retrieval, entity extraction, etc.).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document


class DocumentElement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_elements"
    __table_args__ = (
        # Natural key on (document_id, order) — elements are stable in
        # reading order within a doc.
        UniqueConstraint(
            "document_id", "order_index", name="uq_document_elements_doc_order"
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # unstructured's element kind (free-form string — any extractor's
    # taxonomy works). Common values: Title, NarrativeText, ListItem,
    # Table, Header, Footer, Address, Image.
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    text: Mapped[str] = mapped_column(Text, nullable=False)

    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Position in reading order. Start at 0.
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Per-element passthrough — coordinates, cell structure for tables,
    # languages detected, etc. Whatever the extractor provides.
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=None
    )

    document: Mapped[Document] = relationship(
        back_populates="elements", lazy="selectin"
    )
