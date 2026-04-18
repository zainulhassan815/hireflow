# Search hardening — strategy & edge case map

Reference doc for raising document search to production-grade accuracy
and correctness. Companion to `architecture.md`, `rag-architecture.md`,
and `rag-pipeline.md` (current-state pipeline diagrams).

The implementation is split across four tracker tickets (F86–F89). This
doc explains the *why*, the gap, and what "good" looks like — the
tickets capture the *what to ship*.

---

## 1. Where we are today

Three signals feed Reciprocal Rank Fusion in `SearchService.search`
(`backend/app/services/search_service.py:55`):

| Signal              | Source                                                | Granularity | What it indexes                |
|---------------------|-------------------------------------------------------|-------------|--------------------------------|
| Vector              | ChromaDB cosine distance, distance ceiling filtered   | Chunk       | `extracted_text` chunks (500c) |
| Lexical FTS (F85)   | `ts_rank_cd` over `documents.extracted_text_tsv`      | Document    | `extracted_text` body only     |
| SQL metadata filter | `DocumentRepository.search_by_metadata`               | Document    | Skills/type/dates as **filter**, not ranking |

**What is NOT searched against the user's query:**
- `filename`
- `document_type`
- `metadata.skills`, `metadata.experience_years`, etc.

**What is NOT enforced:**
- Per-user ownership scoping in search (the `documents` endpoints scope
  by owner; search returns every doc to every user — see `routes/search.py:25`)

---

## 2. Production-grade reference architecture

What "good" looks like for document search at production accuracy.
Most modern systems implement some subset of these nine layers:

| # | Layer                                  | Typical implementation                                       | Hireflow status |
|---|----------------------------------------|--------------------------------------------------------------|-----------------|
| 1 | Hybrid retrieval                       | Vector + BM25/FTS, combined via RRF                          | ✅ F80, F85     |
| 2 | Multi-field weighted index             | Title, headings, metadata, body — each weighted              | ❌ → F87        |
| 3 | Cross-encoder reranking                | Rerank merged top-K with a small cross-encoder model         | 🟡 planned F80.5|
| 4 | Query understanding                    | Synonyms, acronyms, spell, expansion                         | ❌ → F88        |
| 5 | Structure-aware chunking               | Section/heading-aligned, not fixed N chars                   | ❌ planned F82  |
| 6 | Result diversity                       | MMR / per-doc cap so one doc doesn't dominate                | 🟡 doc-level dedup in RRF |
| 7 | Access control at retrieval time       | Filter by tenant/owner/role *before* ranking                 | ❌ → F86 (P0)   |
| 8 | Eval harness with golden queries       | Continuous P@5/R@5/MRR tracking; regression alarm            | ✅ F80          |
| 9 | Snippet selection that explains match  | Highlight matched terms; for non-lexical hits, leading sent. | 🟡 partial F92.1|

The reference systems that bundle most of this are Elasticsearch /
OpenSearch / Vespa. Hireflow rebuilds the same primitives on
Postgres + Chroma — fine for our scale, just need to know the shape
we're aiming for.

### Order of accuracy ROI

What actually moves the needle, biggest → smallest:

1. **Multi-field weighted FTS** (F87) — title/filename match is the
   single largest unlock for HR docs because filenames are intentional.
2. **Cross-encoder reranker** (F80.5) — pushes precision once recall is
   good. Eval shape after F85 is exactly the case for this (R@5=0.91,
   P@5=0.24).
3. **Structure-aware chunking** (F82) — uplift compounds across all
   downstream signals.
4. **Acronym / synonym dictionary** (F88) — domain-specific, small but
   real (`JS`/`K8s`/`ML`/`TS`).
5. **Result diversity (MMR)** — diminishing returns until corpus grows.

---

## 3. Edge case catalog

Sorted by impact for our actual use case (HR docs, resumes, contracts),
not academic completeness.

### P0 — correctness bugs (must fix)

| # | Issue                                              | Today's behaviour                                                            | Ticket |
|---|----------------------------------------------------|------------------------------------------------------------------------------|--------|
| 1 | Search ignores ownership                           | Any logged-in user sees every document                                       | F86    |
| 2 | Vector path doesn't filter by `status`             | A `processing` doc with chunks already indexed can surface; FTS path filters | F86    |

### P1 — common user behavior the system handles poorly

| # | Issue                                              | Today                                                                          | Ticket |
|---|----------------------------------------------------|--------------------------------------------------------------------------------|--------|
| 1 | Filename never matched against query               | `menu analyzer` doesn't hit `Menu Analyzer Portfolio Doc.pdf` unless body text | F87    |
| 2 | Empty / whitespace / stopword-only query           | FTS short-circuits to empty, vector returns noise                              | F88    |
| 3 | Phrase queries (`"machine learning"`)              | `plainto_tsquery` ignores quotes — words ANDed but adjacency isn't preferred   | F88    |
| 4 | Acronyms / abbreviations                           | `JS` doesn't match `JavaScript`; `K8s` doesn't match `Kubernetes`              | F88    |
| 5 | Common typos                                       | `pyhton` returns nothing — no fuzzy fallback                                   | F88    |
| 6 | Very long pasted queries (full job descriptions)   | Tokenized into a giant tsquery — slow, low precision                           | F88    |

### P2 — lower frequency but visible

| # | Issue                                              | Today                                                                | Ticket |
|---|----------------------------------------------------|----------------------------------------------------------------------|--------|
| 1 | Special tech tokens (`C++`, `.NET`, `Node.js`, `C#`) | Postgres `english` analyzer strips punctuation; same gap in F92.1's highlight regex | F88 |
| 2 | Negation (`python NOT java`)                       | Not supported by `plainto_tsquery`                                   | F88    |
| 3 | Versions / numbers (`Python 3.12`, `v2.0`)         | Mostly OK; sometimes the version drops out                           | F89    |
| 4 | Mixed-language document bodies                     | English analyzer mismatches; tokens lost                             | F89    |
| 5 | Recency tie-breaking                               | Equal RRF scores → arbitrary order                                   | F89    |
| 6 | Pagination (offset)                                | `limit` exists, no `offset`                                          | F89    |

### P3 — domain-specific HR

| # | Issue                                              | Today                                                                | Ticket |
|---|----------------------------------------------------|----------------------------------------------------------------------|--------|
| 1 | Skill normalization (`python`/`Python`/`py3`)      | Each variant indexed separately                                      | F89 (overlaps F83) |
| 2 | Experience parsing (`5+ years`, `senior`)          | No mapping from prose to numeric range                               | F89 (overlaps F83) |
| 3 | Education hierarchy (`BS < MS < PhD`)              | No ordinal signal                                                    | F89 (overlaps F83) |

---

## 4. Implementation roadmap

Four tickets, sequenced for minimum churn:

### F86 — Search correctness (P0)
- Forward `current_user.owner_id` from the route into the service and
  every retrieval path (vector `where` filter, FTS predicate, SQL
  metadata).
- Decide tenancy model: **per-user** vs **shared HR pool** (open
  question — captured in the ticket). Default to per-user; admin
  bypasses.
- Filter `status = READY` in the vector path.
- Eval: add cases that other-user docs are excluded; non-READY docs are
  excluded.

### F87 — Multi-field weighted FTS (P1 core)
- Migration: replace `extracted_text_tsv` with a weighted `search_tsv`
  generated column:
  - **A** (highest): `filename`
  - **B**: `document_type`, `metadata.skills`, `metadata.summary`
  - **C** (lowest): `extracted_text`
- `ts_rank_cd` automatically respects the weights.
- No code change in `SearchService`; just the repo + migration.
- Eval: add filename-only query cases.

### F88 — Query syntax & understanding (P1 + P2)
- Switch `plainto_tsquery` → `websearch_to_tsquery` (free phrase / OR /
  NOT support).
- Empty / stopword-only / whitespace handling at the service edge.
- Query length cap (e.g. 256 tokens).
- Acronym / synonym map, applied at query time before tokenization
  (start with ~30 HR-domain entries; iterate).
- Typo tolerance via `pg_trgm` extension as a fallback when `ts_rank_cd`
  returns empty.
- Special-token preservation: pre-process `C++`, `.NET`, `Node.js`,
  `C#`, `.NET Core` into safe tokens (`cpp`, `dotnet`, `nodejs`, `csharp`)
  in both index and query paths. Share helper with F92.1's highlight
  tokenizer.

### F89 — Search polish (P2 + P3)
- Recency tie-break: stable order by `created_at desc` when scores
  equal.
- Pagination: add `offset` to `SearchRequest`.
- Mixed-language fallback: if `english` tsvector empty, try `simple`.
- Skill normalization (overlaps F83 candidate matching — coordinate
  via shared canonicalization table).
- Experience parsing helper.

---

## 5. Out of scope

Decisions made deliberately, recorded so we don't relitigate them:

- **Migration to Elasticsearch / OpenSearch** — not at our scale.
  Postgres FTS + pgvector + cross-encoder is sufficient through
  ~10M chunks. Re-evaluate if latency or relevance ceiling becomes
  the blocker.
- **Learning-to-rank with click data** — premature. We need consistent
  user volume first; until then a hand-curated cross-encoder is better
  signal than scarce click data.
- **Per-tenant index sharding** — single Postgres + per-row owner
  filter is fine until we hit multi-org SaaS scale.

---

## 6. Verification approach

For each ticket, the eval harness (`backend/tests/eval/test_search_quality.py`)
gets new golden queries that exercise the specific edge cases. A ticket
is "done" when:

1. Code lands.
2. Unit tests pass.
3. New eval cases pass with no `must_not_contain` violations.
4. Aggregate P@5 / R@5 / MRR don't regress on existing baseline.

Track P@5 across slices in `baseline.json`. Soft floor stays at 0.35
(F80 default) until F87 lands; then raise per the lift observed.
