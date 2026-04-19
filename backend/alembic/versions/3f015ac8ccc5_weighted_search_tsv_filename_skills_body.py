"""weighted search tsv filename skills body

Revision ID: 3f015ac8ccc5
Revises: 59788d6cb64a
Create Date: 2026-04-19 00:56:27.536962

F87: replace the F85 single-field tsvector with a multi-field
weighted version. ``ts_rank_cd`` respects the per-field weights, so
a filename match outranks a body-only mention without any ranking
code change in SearchService.

Weighting:
    A (highest) — filename
    B           — metadata.skills
    C (lowest)  — extracted_text

``document_type`` is intentionally NOT indexed in the tsvector:
``enum::text`` is non-IMMUTABLE in Postgres (the text label can
change via ALTER TYPE), so generated-column expressions reject it.
``document_type`` only has 5 fixed values and is already
filterable as a structured search param — exact SQL filter is the
right tool there, not FTS.

``metadata->>'skills'`` returns the JSON-stringified array
(e.g. ``'["python","docker"]'``) as text. The english analyzer
strips brackets/quotes during tokenization. Relies on ``skills``
being ``list[str]``; both classifiers produce that shape (see
``adapters/classifiers/{llm,rule_based}.py``). If we ever store
skills as ``[{"name":"x"}]`` this expression silently degrades —
re-evaluate the migration then.

Filenames are pre-processed via ``regexp_replace`` to swap
``_-./`` for spaces before tokenization. Without that, the english
analyzer treats ``menu_analyzer_portfolio.pdf`` as a single token
— which means a query for ``menu analyzer`` would never match it.

The explicit ``'english'::regconfig`` cast is required for IMMUTABLE
treatment; without it, Postgres's parser leaves the regconfig
resolution as STABLE and rejects the generated column.

Production note: ``ADD COLUMN ... STORED`` rewrites the table.
Same caveat as F85; in a production cutover, prefer non-stored
+ batched manual backfill during a maintenance window.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f015ac8ccc5"
down_revision: str | Sequence[str] | None = "59788d6cb64a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS documents_extracted_text_tsv_idx")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS extracted_text_tsv")

    op.execute(
        r"""
        ALTER TABLE documents
        ADD COLUMN search_tsv tsvector
        GENERATED ALWAYS AS (
            setweight(
                to_tsvector(
                    'english'::regconfig,
                    coalesce(regexp_replace(filename, '[_\-./]+', ' ', 'g'), '')
                ),
                'A'
            ) ||
            setweight(
                to_tsvector('english'::regconfig, coalesce(metadata->>'skills', '')),
                'B'
            ) ||
            setweight(
                to_tsvector('english'::regconfig, coalesce(extracted_text, '')),
                'C'
            )
        ) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX documents_search_tsv_idx
        ON documents USING GIN (search_tsv)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS documents_search_tsv_idx")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS search_tsv")

    # Restore the F85 single-field column + index.
    op.execute(
        """
        ALTER TABLE documents
        ADD COLUMN extracted_text_tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english'::regconfig, coalesce(extracted_text, ''))
        ) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX documents_extracted_text_tsv_idx
        ON documents USING GIN (extracted_text_tsv)
        """
    )
