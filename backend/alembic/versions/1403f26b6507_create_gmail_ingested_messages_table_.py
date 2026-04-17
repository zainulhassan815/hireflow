"""create gmail_ingested_messages table and add sync activity

Adds the dedup ledger for the Gmail sync worker and extends the
``activity_action`` enum with ``gmail_sync_run``. Enum growth runs
inside an ``autocommit_block`` because ``ALTER TYPE ... ADD VALUE``
cannot run inside a transaction.

Revision ID: 1403f26b6507
Revises: afa74e4e185d
Create Date: 2026-04-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "1403f26b6507"
down_revision: str | Sequence[str] | None = "afa74e4e185d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE activity_action ADD VALUE IF NOT EXISTS 'gmail_sync_run'"
        )

    op.create_table(
        "gmail_ingested_messages",
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=255), nullable=False),
        sa.Column(
            "ingest_status",
            sa.Enum(
                "claimed",
                "completed",
                "failed",
                "reset",
                name="gmail_ingest_status",
            ),
            nullable=False,
            server_default="claimed",
        ),
        sa.Column("attachment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "document_ids",
            postgresql.ARRAY(sa.UUID()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
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
            ["connection_id"], ["gmail_connections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "gmail_message_id",
            name="uq_gmail_ingested_connection_message",
        ),
    )
    op.create_index(
        op.f("ix_gmail_ingested_messages_connection_id"),
        "gmail_ingested_messages",
        ["connection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gmail_ingested_messages_ingest_status"),
        "gmail_ingested_messages",
        ["ingest_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_gmail_ingested_messages_ingest_status"),
        table_name="gmail_ingested_messages",
    )
    op.drop_index(
        op.f("ix_gmail_ingested_messages_connection_id"),
        table_name="gmail_ingested_messages",
    )
    op.drop_table("gmail_ingested_messages")
    op.execute("DROP TYPE IF EXISTS gmail_ingest_status")
    # Postgres does not support removing enum values; ``gmail_sync_run``
    # stays on ``activity_action``. Harmless.
