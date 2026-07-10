"""candidate_attachments + supplementary_keywords (F46.a)

Revision ID: a1c2e3f4b5d6
Revises: d3f8a1b4c7e2
Create Date: 2026-07-11 10:00:00.000000

Makes a candidate a bundle of files instead of a single resume:

- ``attachment_role`` enum (resume / certificate / portfolio /
  cover_letter / transcript / other).
- ``candidate_attachments`` join table with a unique
  ``(candidate_id, document_id)`` constraint. Both FKs cascade on
  delete so removing a candidate or a document tidies the join rows.
- ``candidates.supplementary_keywords`` (text[] NULL) for softer
  signal merged from non-resume attachments.

Backfill: every candidate with a ``source_document_id`` gets a
``role=resume`` attachment so downstream code has one traversal and the
resume pointer stays coherent with the join table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1c2e3f4b5d6"
down_revision: str | Sequence[str] | None = "d3f8a1b4c7e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# create_type=False so create_table() below doesn't auto-emit a second
# CREATE TYPE for the column — we create/drop the enum explicitly.
_attachment_role = postgresql.ENUM(
    "resume",
    "certificate",
    "portfolio",
    "cover_letter",
    "transcript",
    "other",
    name="attachment_role",
    create_type=False,
)


def upgrade() -> None:
    _attachment_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "candidate_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            _attachment_role,
            nullable=False,
        ),
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
            ["candidate_id"], ["candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_candidate_attachments_candidate_id",
        "candidate_attachments",
        ["candidate_id"],
    )
    op.create_index(
        "ix_candidate_attachments_document_id",
        "candidate_attachments",
        ["document_id"],
    )
    op.create_index(
        "ix_candidate_attachments_candidate_document_unique",
        "candidate_attachments",
        ["candidate_id", "document_id"],
        unique=True,
    )

    op.add_column(
        "candidates",
        sa.Column(
            "supplementary_keywords",
            postgresql.ARRAY(sa.String()),
            nullable=True,
        ),
    )

    # Backfill: existing resume pointers become role=resume attachments.
    op.execute(
        """
        INSERT INTO candidate_attachments
            (id, candidate_id, document_id, role, created_at, updated_at)
        SELECT gen_random_uuid(), c.id, c.source_document_id, 'resume', now(), now()
        FROM candidates c
        WHERE c.source_document_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("candidates", "supplementary_keywords")
    op.drop_index(
        "ix_candidate_attachments_candidate_document_unique",
        table_name="candidate_attachments",
    )
    op.drop_index(
        "ix_candidate_attachments_document_id", table_name="candidate_attachments"
    )
    op.drop_index(
        "ix_candidate_attachments_candidate_id", table_name="candidate_attachments"
    )
    op.drop_table("candidate_attachments")
    _attachment_role.drop(op.get_bind(), checkfirst=True)
