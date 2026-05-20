# 04 · Lexical & fuzzy index

The Postgres side of search: weighted `search_tsv`, `ts_rank_cd`,
`websearch_to_tsquery`, and the `pg_trgm` fallback that catches typos.

---

## Purpose

Be the lexical counterweight to the vector index. Vector search misses
rare tokens, exact names, and out-of-vocabulary terms (filenames,
project codes). The FTS path is cheap, exact-biased, and ranks by
weighted field so filename matches outrank body matches.

Plus a trigram fallback so a user who types `pyhton` or `brightforg`
still finds the right doc.

---

## Flow

### Index (auto, at every Postgres write)

```
documents.search_tsv  (GENERATED STORED tsvector)
     │
     │  defined in Alembic migration 2347719a1bd8
     │
     ▼
  setweight(to_tsvector('english', normalize_tech_tokens(
       regexp_replace(filename, '[_\-./]+', ' ', 'g'))), 'A')
  ||
  setweight(to_tsvector('english',
       coalesce(metadata->>'skills', '')), 'B')
  ||
  setweight(to_tsvector('english', normalize_tech_tokens(
       coalesce(extracted_text, ''))), 'C')
```

Weights matter for `ts_rank_cd`:

| Weight | Field | Rationale |
|--------|-------|-----------|
| A | filename (with `_-./` → space) | Filenames are intentional. `menu_analyzer.pdf` should rank for "menu analyzer". |
| B | `metadata.skills` | Classifier-extracted skills are high-signal structured data. |
| C | `extracted_text` | Body text — relevant but noisy. |

`normalize_tech_tokens` (SQL function; **must** mirror
`app/services/query_expansion.py::normalize_tech_tokens`) substitutes
`C++ → cpp`, `Node.js → nodejs`, `.NET → dotnet`, etc. The english
analyzer strips `+`, `#`, `.`, which would otherwise erase those
tokens. Both sides (index + query) run the same substitution.

`document_type` is deliberately **not** in the tsvector — the enum
cast isn't IMMUTABLE, and the metadata/SQL path handles the 5 doc
types better as a structured filter.

### Query — FTS path

```
lexical_query = expand_acronyms(normalize_tech_tokens(raw_query))
     │
     ▼
full_text_search (repositories/document.py:228)
     │  if len > 1024 → truncate  (F88.a)
     │  ts_query = websearch_to_tsquery('english', lexical_query)
     │  rank     = ts_rank_cd(search_tsv, ts_query)
     │
     │  WHERE status = READY
     │    AND search_tsv @@ ts_query
     │    AND owner_id = :owner  (HR) or skipped (admin)
     │    AND document_type = :type (if provided)
     │  ORDER BY rank DESC LIMIT N
     ▼
list[(Document, rank)]
```

`websearch_to_tsquery` — chosen in F88.a for:

- Quoted phrases (`"machine learning"` keeps tokens adjacent).
- Explicit OR (`python OR golang`).
- Negation (`python -java`).
- Graceful handling of junk (parses loose, never raises).

`expand_acronyms` (`services/query_expansion.py:60`) swaps `k8s →
kubernetes`, `ml → machine learning`, etc. Only applied to the FTS
side — vector embedders handle equivalence semantically.

### Query — fuzzy fallback

```
if full_text_search returned 0 hits:
     │
     ▼
fuzzy_search (repositories/document.py:289)
     │  sim_filename = strict_word_similarity(query, filename)
     │  sim_body     = strict_word_similarity(query, coalesce(extracted_text, ''))
     │  sim          = GREATEST(sim_filename, sim_body)
     │
     │  WHERE status = READY AND sim >= 0.25
     │    AND owner_id = :owner (HR) AND document_type = :type (if any)
     │  ORDER BY sim DESC LIMIT N
     ▼
list[(Document, sim)]
```

`strict_word_similarity` (not plain `word_similarity`) requires the
matched window to align with word boundaries. On long body text the
plain variant produces noise (~0.28 unrelated); strict cleanly separates
real matches (~0.27 for a single-letter typo on "python") from
noise (~0.13-0.17).

Filename trigrams hit `documents_filename_trgm_idx` (GIN). Body
trigrams scan unindexed — fine today, would need a GIN index if the
corpus grows hot enough to matter.

---

## Key invariants

- **Both sides of the tech-token substitution run in sync.**
  `app/services/query_expansion.py::normalize_tech_tokens` and the
  SQL `normalize_tech_tokens(text)` function must produce identical
  output for identical input. A mismatch silently drops matches.
  There's a test in `tests/test_document_fts.py` that indexes via
  the SQL path and queries via the Python path to catch drift.
- **FTS query is normalized + acronym-expanded, vector is raw.**
  Pre-normalizing the vector query just adds noise to the embedder.
- **Fuzzy runs only on zero FTS hits.** Running it always would
  muddy good queries; running it never would fail on typos.
- **`document_type` is a structured filter, not an FTS term.**
  `SearchService` handles it as a `where` clause — not a tsvector
  weight. Keeps the FTS path small and the filter exact.
- **All paths enforce `status = READY` and `owner_id` scoping.**
  Mirrors `DocumentService._ensure_access`. No path can leak
  unready / other-owner docs.

---

## Configuration knobs

| Setting | Default | Effect |
|---------|---------|--------|
| `_MAX_QUERY_CHARS` (const) | 1024 | Truncate long pasted queries. |
| `_TRGM_THRESHOLD` (const) | 0.25 | Min strict similarity for fuzzy to return a doc. |

Both live in `app/repositories/document.py`. Promote to env vars if
they start needing tuning per-environment.

---

## Known issues / pain points

1. **`plainto_tsquery` semantics for multi-word unquoted queries
   are still AND.** Good for precision, bad for recall when the user
   types a long loose query. `websearch_to_tsquery` inherits this —
   `"python machine learning"` requires all three words. The fuzzy
   fallback only fires on *zero* hits, not low-recall hits. See
   `docs/search-hardening.md` §3 P1-6.

2. **English analyzer drops tokens on mixed-language bodies.** A
   resume with a French cover letter section silently loses half
   its tokens. F89 has an entry for a `simple` analyzer fallback;
   not shipped.

3. **Version/numeric tokens are brittle.** `Python 3.12` tokenizes
   as `python` + `3.12` — the number survives but doesn't carry
   meaning for retrieval. `node 18` vs `node.js 18` reach different
   outcomes. Minor; hits rarely enough to defer.

4. **Body-side trigram scan is unindexed.** Fine for ≤10k docs; would
   start hurting at 100k. Solution is a GIN trigram index on
   `extracted_text` — a migration away.

5. **Tech-token substitutions are SQL-duplicated.** Adding a new
   entry means editing `_TECH_TOKEN_SUBSTITUTIONS` in
   `query_expansion.py` **and** writing a new Alembic migration for
   the SQL function. Easy to miss one side. Protected by the
   `test_document_fts.py` integration test, but still error-prone.

6. **Acronym list is one-directional** — `k8s → kubernetes` works,
   but a doc that says `k8s` and a query that says `kubernetes`
   relies on embedding similarity (fine) or document-side expansion
   (not done). Intentional, but worth knowing.

7. **Negation (`-java`) only affects FTS.** The vector RRF branch
   still surfaces Java-heavy docs. Documented limitation from F88.
   A fix would require post-RRF negation filtering or dropping
   negation-matching docs from vector hits; both are more effort
   than today's product needs.

8. **Ambiguous acronyms are omitted.** `cv` (curriculum vitae vs
   computer vision), `tf` (terraform vs tensorflow) — no expansion.
   Correct for precision; a downstream fallback could disambiguate
   by context ("cv" alongside "resume" → curriculum vitae).

9. **Trigram threshold doesn't adapt to query length.** A 3-char
   query has wildly different similarity distribution than a 20-char
   query. Today one fixed threshold; short queries sometimes miss.

10. **No recency tie-break** on equal FTS ranks. Arbitrary order
    when `ts_rank_cd` is tied. Scoped in F89 ("stable `created_at desc`").

---

## Improvement opportunities

### Short-term

- **Recency tie-break.** Change `ORDER BY rank DESC` to
  `ORDER BY rank DESC, created_at DESC` in both `full_text_search`
  and `fuzzy_search`. Trivial; fixes a user-visible flicker on
  repeated queries.
- **Simple-analyzer fallback.** Try `simple` tsvector when
  `english` produces empty ts_query (detect via `numnode(ts_query)=0`
  on the query side). Lifts recall on non-English docs without
  hurting English.
- **Body trigram GIN index** — `CREATE INDEX ... USING gin
  (extracted_text gin_trgm_ops);` — one migration. Pays for itself
  once body-fuzzy becomes a regular fallback target.
- **Consolidate tech-token substitutions** into a shared JSON
  fixture consumed by both the Alembic migration (via
  `pg_read_binary_file`) and the Python module. Single source of
  truth, lint failure on drift.

### Medium-term

- **Field-specific query hints.** Parse
  `filename:"alice_resume.pdf"` / `type:resume` / `skill:python`
  (F89 scope) and route those subexpressions to SQL filters
  directly rather than through tsquery. Gives power users an escape
  hatch and reduces mis-ranking.
- **Query expansion beyond one-directional acronyms.** Role-family
  (`frontend → React/Vue/Angular`) — see F89.d. Conservative
  taxonomy with eval-gated precision guards.
- **Adaptive trigram threshold.** `_TRGM_THRESHOLD` scaled by query
  length: `max(0.18, 0.35 - 0.01*len(query))`. Catches short typos
  without muddying long queries.
- **Log lexical-vs-fuzzy fallthrough** counter. Helps calibrate the
  threshold and justify (or retire) the fuzzy path.

### Long-term

- **Learning-to-rank on ts_rank_cd output** — mix in click data,
  freshness, owner engagement signals. Scoped out in
  `docs/search-hardening.md` §5. Premature until we have traffic.
- **Replace FTS + trigram with a managed text index** (Meilisearch,
  Typesense). Keeps Postgres for metadata; text quality jumps.
  Only justified once latency or relevance ceiling becomes the
  blocker — `search-hardening.md` §5 says not yet.
- **Multi-language analyzer routing** — detect doc language at
  extraction, pick `to_tsvector('<lang>', ...)` accordingly. Needs a
  language-detection step in extraction and a migration to support
  multiple tsvectors per doc.

---

## Cross-references

- **Code**: `backend/app/repositories/document.py`,
  `app/services/query_expansion.py`,
  Alembic migration `2347719a1bd8` (weighted tsvector + SQL
  `normalize_tech_tokens`), `tests/test_document_fts.py`.
- **Related flows**: `05-query-understanding.md`,
  `06-hybrid-search.md`.
- **Design**: `docs/search-hardening.md` §3/§4,
  `docs/features.md` F85, F87, F88.
