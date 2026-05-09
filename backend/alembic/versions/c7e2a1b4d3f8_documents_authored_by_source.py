"""documents.authored_by_source + activity_action author values

Revision ID: c7e2a1b4d3f8
Revises: 44a5691108b2
Create Date: 2026-05-09 20:30:00.000000

F103.c.2 — distinguishes operator-set author links from inferred
ones, and adds two new ``activity_action`` enum values for the
audit trail of manual link/unlink operations.

Three changes in one revision:

1. New Postgres ENUM ``documents_authored_by_source`` (values:
   ``email_match``, ``manual``).
2. New nullable column ``documents.authored_by_source`` referencing
   that ENUM.
3. Idempotency-guarded backfill: rows where ``authored_by_id IS
   NOT NULL AND authored_by_source IS NULL`` get
   ``authored_by_source = 'email_match'`` (every existing F103.c
   FK was set by the email-match heuristic). The ``IS NULL`` guard
   makes the migration safe to re-run if a deployment race ever
   leaves the column without the backfill.
4. Two new ``activity_action`` values (``document_author_set``,
   ``document_author_cleared``). Postgres requires ``ALTER TYPE
   ... ADD VALUE`` to run outside a transaction, so it's wrapped
   in ``op.get_context().autocommit_block()``.

Dangling-source caveat: when a candidate is deleted, the FK becomes
NULL via the ``ON DELETE SET NULL`` rule from F103.c, but
``authored_by_source`` stays at its prior value. Every reader
checks ``authored_by_id IS NOT NULL`` first; the dangling source
is benign. No SQL trigger to chase it.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7e2a1b4d3f8"
down_revision: str | Sequence[str] | None = "44a5691108b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_AUTHOR_SOURCE_ENUM = "documents_authored_by_source"
_AUTHOR_SOURCE_VALUES = ("email_match", "manual")


def upgrade() -> None:
    # --- ENUM type + column ---
    author_source = sa.Enum(
        *_AUTHOR_SOURCE_VALUES,
        name=_AUTHOR_SOURCE_ENUM,
    )
    author_source.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "documents",
        sa.Column(
            "authored_by_source",
            sa.Enum(*_AUTHOR_SOURCE_VALUES, name=_AUTHOR_SOURCE_ENUM),
            nullable=True,
        ),
    )

    # --- Idempotency-guarded backfill ---
    op.execute(
        """
        UPDATE documents
        SET authored_by_source = 'email_match'
        WHERE authored_by_id IS NOT NULL
          AND authored_by_source IS NULL
        """
    )

    # --- New activity_action values (must run outside a transaction) ---
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE activity_action ADD VALUE IF NOT EXISTS 'document_author_set'"
        )
        op.execute(
            "ALTER TYPE activity_action ADD VALUE IF NOT EXISTS 'document_author_cleared'"
        )


def downgrade() -> None:
    # Drop the column first, then the ENUM type.
    op.drop_column("documents", "authored_by_source")
    sa.Enum(name=_AUTHOR_SOURCE_ENUM).drop(op.get_bind(), checkfirst=True)
    # Postgres ENUM doesn't support removing values cleanly; the two
    # new ``activity_action`` values stay (harmless — code stops
    # writing them when the F103.c.2 routes downgrade with the
    # column).
