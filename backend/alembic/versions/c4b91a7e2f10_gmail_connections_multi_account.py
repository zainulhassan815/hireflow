"""gmail_connections: allow multiple accounts per user

Replaces ``UNIQUE (user_id)`` with ``UNIQUE (user_id, gmail_email)`` so
one HR user can connect more than one mailbox. See
``docs/dev/F53a-multi-gmail-accounts/``.

Upgrade is data-safe: the old single-column unique already guaranteed
at most one row per user, which is trivially unique on the composite.
Downgrade collapses any duplicate (user_id) rows (oldest wins) before
reinstating the single-column unique.

Revision ID: c4b91a7e2f10
Revises: a91b3c2d4e5f
Create Date: 2026-04-22

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4b91a7e2f10"
down_revision: str | Sequence[str] | None = "a91b3c2d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "gmail_connections_user_id_key", "gmail_connections", type_="unique"
    )
    op.create_unique_constraint(
        "uq_gmail_connections_user_email",
        "gmail_connections",
        ["user_id", "gmail_email"],
    )


def downgrade() -> None:
    # Collapse duplicates before narrowing the unique constraint. Keeps
    # the oldest row per user so the survivor matches the pre-F53 world
    # (the row that was originally written under UNIQUE (user_id)).
    op.execute(
        """
        DELETE FROM gmail_connections g
        USING gmail_connections g2
        WHERE g.user_id = g2.user_id
          AND g.created_at > g2.created_at
        """
    )
    op.drop_constraint(
        "uq_gmail_connections_user_email", "gmail_connections", type_="unique"
    )
    op.create_unique_constraint(
        "gmail_connections_user_id_key", "gmail_connections", ["user_id"]
    )
