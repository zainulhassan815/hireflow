"""conversations + chat_messages

Persistence layer for chat (F96). Two tables plus a ``chat_role`` enum.

The enum is created fresh rather than extended, so no ``ALTER TYPE``
autocommit block is needed. Downgrade drops it explicitly — Postgres
does not remove a type when the last column using it goes away.

Revision ID: c5d9e731a8b4
Revises: b8e4f16d3a29
Create Date: 2026-09-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c5d9e731a8b4"
down_revision: str | Sequence[str] | None = "b8e4f16d3a29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE_VALUES = ("user", "assistant")
_ROLE_ENUM = "chat_role"


def upgrade() -> None:
    postgresql.ENUM(*_ROLE_VALUES, name=_ROLE_ENUM).create(
        op.get_bind(), checkfirst=True
    )

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column(
            "archived", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
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
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_owner_id", "conversations", ["owner_id"], unique=False
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            # create_type=False: the type is created above, once. Left to
            # itself create_table would emit a second CREATE TYPE and fail.
            postgresql.ENUM(*_ROLE_VALUES, name=_ROLE_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("intent", sa.String(length=32), nullable=True),
        sa.Column("intent_confidence", sa.Float(), nullable=True),
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
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_messages_conversation_created",
        "chat_messages",
        ["conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_conversation_created", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_conversations_owner_id", table_name="conversations")
    op.drop_table("conversations")
    postgresql.ENUM(name=_ROLE_ENUM).drop(op.get_bind(), checkfirst=True)
