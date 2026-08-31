"""gmail_connections: backfill cursor columns

Adds the two columns that drive batched historical sync:

* ``backfill_before`` — exclusive upper bound of the next batch, and the
  "is backfilling" flag. NULL means no backfill in progress.
* ``backfill_until`` — the floor the walk stops at.

Both nullable with no server default, so existing rows are untouched and
keep their current incremental-only behaviour.

Revision ID: f3a7d21c9b04
Revises: a1c2e3f4b5d6
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3a7d21c9b04"
down_revision: str | Sequence[str] | None = "a1c2e3f4b5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gmail_connections",
        sa.Column("backfill_before", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "gmail_connections",
        sa.Column("backfill_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gmail_connections", "backfill_until")
    op.drop_column("gmail_connections", "backfill_before")
