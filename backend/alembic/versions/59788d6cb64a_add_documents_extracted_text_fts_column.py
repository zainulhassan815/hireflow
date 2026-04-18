"""add documents extracted_text fts column

Revision ID: 59788d6cb64a
Revises: 1403f26b6507
Create Date: 2026-04-19 00:02:55.135342

F85: lexical retrieval. Adds a Postgres-generated tsvector column
over `documents.extracted_text` plus a GIN index, enabling
ts_rank_cd-based ranking next to the existing vector search.

The column is STORED + GENERATED ALWAYS so it auto-backfills on
add and auto-updates on extracted_text writes — no triggers, no
worker code change.

Production note: ADD COLUMN ... STORED rewrites the whole table.
Acceptable in dev; in a real production cutover, prefer
non-stored + manual backfill in batches during a maintenance
window.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "59788d6cb64a"
down_revision: str | Sequence[str] | None = "1403f26b6507"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE documents
        ADD COLUMN extracted_text_tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english', coalesce(extracted_text, ''))
        ) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX documents_extracted_text_tsv_idx
        ON documents USING GIN (extracted_text_tsv)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS documents_extracted_text_tsv_idx")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS extracted_text_tsv")
