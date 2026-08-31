"""gmail change detection + opt-in deletion mirroring

Adds:

* ``gmail_connections.last_history_id`` — cursor into Gmail's history
  feed. Null re-seeds on the next run.
* ``gmail_connections.mirror_deletions`` — opt-in. Existing rows get
  ``false`` via server default, so no connection starts deleting
  documents because this migration ran.
* ``gmail_ingested_messages.source_deleted_at`` — when Gmail last
  reported the source message trashed or deleted. Recorded whether or
  not mirroring is on.
* ``activity_action`` gains ``gmail_settings_update`` so flipping the
  mirroring switch is auditable under its own name. Postgres keeps
  enum values on downgrade — dropping one would break existing rows.

Revision ID: b8e4f16d3a29
Revises: f3a7d21c9b04
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8e4f16d3a29"
down_revision: str | Sequence[str] | None = "f3a7d21c9b04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE must run outside the migration's transaction.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE activity_action ADD VALUE IF NOT EXISTS 'gmail_settings_update'"
        )

    op.add_column(
        "gmail_connections",
        sa.Column("last_history_id", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "gmail_connections",
        sa.Column(
            "mirror_deletions",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "gmail_ingested_messages",
        sa.Column("source_deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gmail_ingested_messages", "source_deleted_at")
    op.drop_column("gmail_connections", "mirror_deletions")
    op.drop_column("gmail_connections", "last_history_id")
