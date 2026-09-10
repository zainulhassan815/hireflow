"""gmail reauth marker + per-owner document content hash

Two defences against re-importing the same mail after a reconnect.

``gmail_connections.reauth_required_at`` lets a dead refresh token mark
the connection instead of deleting it, so the ingest ledger survives and
``UNIQUE (user_id, gmail_email)`` lands a reconnect on the same row.

``documents.content_sha256`` with ``UNIQUE (owner_id, content_sha256)``
makes re-ingesting identical bytes idempotent regardless of how they
arrive. It is nullable on purpose: Postgres treats NULLs as distinct, so
the constraint can land on a table of existing rows without a backfill
in the same migration. ``scripts/dedupe_documents.py`` backfills.

Revision ID: a7b3e91d5c62
Revises: c5d9e731a8b4
Create Date: 2026-09-10

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7b3e91d5c62"
down_revision: str | Sequence[str] | None = "c5d9e731a8b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE must run outside the migration's transaction.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE activity_action ADD VALUE IF NOT EXISTS 'gmail_reauth_required'"
        )

    op.add_column(
        "gmail_connections",
        sa.Column("reauth_required_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_documents_owner_content", "documents", ["owner_id", "content_sha256"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_documents_owner_content", "documents", type_="unique")
    op.drop_column("documents", "content_sha256")
    op.drop_column("gmail_connections", "reauth_required_at")
    # The enum value stays: Postgres cannot drop one, and existing rows
    # may already reference it.
