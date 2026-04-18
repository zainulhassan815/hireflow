"""enable pg_trgm and trigram index on filename

Revision ID: deea2df97ed9
Revises: 3f015ac8ccc5
Create Date: 2026-04-19 01:14:36.168978

F88.c: typo tolerance via Postgres trigram similarity. The new
index supports the ``fuzzy_search`` repo method, which the search
service falls back to only when FTS returns zero hits — so the
trigram fuzziness doesn't degrade ranking on good queries.

Trigram on filename only (not extracted_text). Filename indexes
stay tiny — average filename ~30 chars — and the most common typo
case is the user mis-spelling a doc title.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "deea2df97ed9"
down_revision: str | Sequence[str] | None = "3f015ac8ccc5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE INDEX documents_filename_trgm_idx
        ON documents USING GIN (filename gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS documents_filename_trgm_idx")
    # Leave the extension installed — other features may rely on it
    # later. Dropping CREATE EXTENSION on downgrade is rarely the
    # right move.
