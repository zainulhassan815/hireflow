"""candidate: unique (owner_id, email) where email is not null

Revision ID: a91b3c2d4e5f
Revises: 93c44e158695
Create Date: 2026-04-20 03:35:00.000000

Re-ingesting a resume (different source_document_id, same person) was
silently creating duplicate candidates. The existing unique constraint
on ``source_document_id`` only deduplicates across reprocesses of the
same document; nothing enforced one-candidate-per-person-per-owner.

Partial unique index handles the nullable ``email`` column: NULLs are
exempt, so candidates without parsed emails still insert freely.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a91b3c2d4e5f"
down_revision: str | Sequence[str] | None = "93c44e158695"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_candidates_owner_email_unique",
        "candidates",
        ["owner_id", "email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_candidates_owner_email_unique", table_name="candidates")
