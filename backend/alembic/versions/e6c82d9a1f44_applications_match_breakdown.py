"""applications: add match_breakdown JSONB

F44.d.6 — store the per-signal breakdown (skill overlap / experience
fit / vector similarity) that ``MatchingService`` already computes, so
the candidate-list hover popover can render "why this score" without
re-running the match.

Nullable: pre-existing application rows don't have a breakdown yet.
Running "Refresh scores" on a job re-computes + populates via the
updated ``MatchingService``.

Revision ID: e6c82d9a1f44
Revises: d82a5f4e9c18
Create Date: 2026-04-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e6c82d9a1f44"
down_revision: str | Sequence[str] | None = "d82a5f4e9c18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column(
            "match_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("applications", "match_breakdown")
