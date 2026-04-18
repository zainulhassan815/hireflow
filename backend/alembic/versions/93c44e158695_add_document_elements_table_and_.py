"""add document_elements table and pipeline version columns

Revision ID: 93c44e158695
Revises: 2347719a1bd8
Create Date: 2026-04-19 03:16:30.641779

F82.d: layout-aware extraction produces typed elements. Persist them
so re-chunking doesn't re-run the slow extractor. Version columns on
documents enable targeted re-index.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "93c44e158695"
down_revision: str | Sequence[str] | None = "2347719a1bd8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_elements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "order_index", name="uq_document_elements_doc_order"
        ),
    )
    op.create_index(
        op.f("ix_document_elements_document_id"),
        "document_elements",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_elements_kind"),
        "document_elements",
        ["kind"],
        unique=False,
    )

    op.add_column(
        "documents",
        sa.Column("extraction_version", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("chunking_version", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "embedding_model_version", sa.String(length=128), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "embedding_model_version")
    op.drop_column("documents", "chunking_version")
    op.drop_column("documents", "extraction_version")
    op.drop_index(
        op.f("ix_document_elements_kind"), table_name="document_elements"
    )
    op.drop_index(
        op.f("ix_document_elements_document_id"), table_name="document_elements"
    )
    op.drop_table("document_elements")
