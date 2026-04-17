"""create gmail_connections table

Adds the table that holds one encrypted Gmail OAuth refresh token per
user, and extends the ``activity_action`` enum with two new values
(``gmail_connect`` / ``gmail_disconnect``) so those events can be
audited via the existing activity log.

Revision ID: afa74e4e185d
Revises: abcc24b78e0c
Create Date: 2026-04-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import app.core.encryption
from alembic import op

revision: str = "afa74e4e185d"
down_revision: str | Sequence[str] | None = "abcc24b78e0c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE must run outside the migration's transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE activity_action ADD VALUE IF NOT EXISTS 'gmail_connect'")
        op.execute(
            "ALTER TYPE activity_action ADD VALUE IF NOT EXISTS 'gmail_disconnect'"
        )

    op.create_table(
        "gmail_connections",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("gmail_email", sa.String(length=320), nullable=False),
        sa.Column(
            "refresh_token", app.core.encryption.EncryptedString(), nullable=False
        ),
        sa.Column("scopes", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("gmail_connections")
    # Postgres does not support removing enum values; the extra
    # ``gmail_connect`` / ``gmail_disconnect`` members stay on the type.
    # Harmless.
