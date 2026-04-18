r"""normalize tech tokens in search_tsv

Revision ID: 2347719a1bd8
Revises: deea2df97ed9
Create Date: 2026-04-19 01:20:00.904267

F88.d: preserve special tech tokens (``C++``, ``C#``, ``F#``,
``.NET``, ``Node.js``, ``Objective-C``) that the english analyzer
would otherwise strip. Adds an IMMUTABLE SQL function that
substitutes these tokens with safe alphabetic equivalents
(``cpp``, ``csharp``, ``fsharp``, ``dotnet``, ``nodejs``,
``objectivec``), then rebuilds ``search_tsv`` to apply it on
both filename and body.

The same substitutions are mirrored in
``app/services/query_expansion.py::normalize_tech_tokens`` —
both sides must stay in sync or queries silently miss matches.
The mirror is small (6 entries) and documented at both ends.

The ``\m`` / ``\M`` word-boundary anchors prevent over-replacement
inside larger tokens (e.g. ``CC++Suite`` won't become ``CCcppSuite``).
``.NET`` uses only ``\M`` because ``\m`` requires a leading
word-character — ``.`` isn't one — so the anchor would never match.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2347719a1bd8"
down_revision: str | Sequence[str] | None = "deea2df97ed9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION normalize_tech_tokens(input text)
        RETURNS text
        LANGUAGE SQL IMMUTABLE PARALLEL SAFE AS $$
            SELECT regexp_replace(
                     regexp_replace(
                       regexp_replace(
                         regexp_replace(
                           regexp_replace(
                             regexp_replace(coalesce(input, ''),
                               'Objective-C',  'objectivec', 'gi'),
                             'Node\.js',       'nodejs',     'gi'),
                           '\mC\+\+',          'cpp',        'gi'),
                         '\mC#',               'csharp',     'gi'),
                       '\mF#',                 'fsharp',     'gi'),
                     '\.NET\M',                'dotnet',     'gi')
        $$
        """
    )

    op.execute("DROP INDEX IF EXISTS documents_search_tsv_idx")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS search_tsv")

    op.execute(
        r"""
        ALTER TABLE documents
        ADD COLUMN search_tsv tsvector
        GENERATED ALWAYS AS (
            setweight(
                to_tsvector(
                    'english'::regconfig,
                    coalesce(
                        normalize_tech_tokens(
                            regexp_replace(filename, '[_\-./]+', ' ', 'g')
                        ),
                        ''
                    )
                ),
                'A'
            ) ||
            setweight(
                to_tsvector(
                    'english'::regconfig,
                    coalesce(metadata->>'skills', '')
                ),
                'B'
            ) ||
            setweight(
                to_tsvector(
                    'english'::regconfig,
                    coalesce(normalize_tech_tokens(extracted_text), '')
                ),
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

    # Restore F87 column without the normalize_tech_tokens wrapper.
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
    op.execute("DROP FUNCTION IF EXISTS normalize_tech_tokens(text)")
