"""documents.authored_by_id FK to candidates

Revision ID: 44a5691108b2
Revises: e6c82d9a1f44
Create Date: 2026-05-09 18:02:54.057189

Adds the F103.c author-linkage FK so non-resume documents (portfolios,
case studies, contracts) can attribute back to a candidate. Today
``Candidate.source_document_id`` already points one way (candidate →
its resume); this adds the reverse-and-broader edge.

Deliberate cyclic FK graph: ``candidates.source_document_id`` →
``documents.id`` and ``documents.authored_by_id`` → ``candidates.id``.
Postgres handles cycles fine at runtime. ``pg_dump`` / ``pg_restore``
needs ``--disable-triggers`` (or correct topological load order) to
load both tables with mutual FKs intact.

Both edges use ``ON DELETE SET NULL``: deleting a candidate nulls
``Document.authored_by_id`` rows; deleting a document nulls
``Candidate.source_document_id``. No cascade loops.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "44a5691108b2"
down_revision: str | Sequence[str] | None = "e6c82d9a1f44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("authored_by_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_documents_authored_by_id",
        "documents",
        ["authored_by_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_documents_authored_by_id_candidates",
        "documents",
        "candidates",
        ["authored_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_documents_authored_by_id_candidates",
        "documents",
        type_="foreignkey",
    )
    op.drop_index("ix_documents_authored_by_id", table_name="documents")
    op.drop_column("documents", "authored_by_id")
