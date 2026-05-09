"""candidates.summary + summary_version (F104.a)

Revision ID: d3f8a1b4c7e2
Revises: c7e2a1b4d3f8
Create Date: 2026-05-09 21:30:00.000000

F104.a — adds two columns on ``candidates``:

- ``summary VARCHAR(1024) NULL`` — the LLM-generated one-line
  recruiter brief, rendered in RAG context as the "anchor" for
  who/which-person-shaped questions. NULL until the runtime path
  or the backfill script generates it.
- ``summary_version VARCHAR(32) NULL`` — version tag stamped
  alongside the summary so a prompt rewrite can be detected by
  the backfill script (skip when version matches; bump the
  ``SUMMARY_VERSION`` constant to force a regenerate). Mirrors
  F103.b/c/d's version-stamp pattern.

Both nullable so existing rows stay valid and the runtime path
can populate progressively.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d3f8a1b4c7e2"
down_revision: str | Sequence[str] | None = "c7e2a1b4d3f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column("summary", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "candidates",
        sa.Column("summary_version", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidates", "summary_version")
    op.drop_column("candidates", "summary")
