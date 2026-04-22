"""documents: add viewable_kind + viewable_key columns

Adds two nullable columns that the F105 viewer pipeline uses to
persist the canonical render asset produced at ingest time. Both
default to NULL for existing rows; the render path falls back to
``storage_key`` when ``viewable_key`` is null, so back-compat is
automatic.

Revision ID: d82a5f4e9c18
Revises: c4b91a7e2f10
Create Date: 2026-04-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d82a5f4e9c18"
down_revision: str | Sequence[str] | None = "c4b91a7e2f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("viewable_kind", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("viewable_key", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "viewable_key")
    op.drop_column("documents", "viewable_kind")
