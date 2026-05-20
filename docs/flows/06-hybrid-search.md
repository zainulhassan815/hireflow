# 06 · Hybrid search

`POST /search` end-to-end: query → parser → four retrieval signals →
weighted RRF → optional rerank → hydrate → highlight → response.

---

## Purpose

Return the best K documents for a natural-language query with enough
signal for the UI to show highlights, confidence, and filters used.
Deterministic, explainable ranking that combines:

- **Vector** semantic similarity (Chroma) — captures paraphrase,
  meaning.
- **Weighted FTS** (Postgres `search_tsv`) — filename / skills /
  body, weighted A/B/C.
- **SQL metadata filter** — only engages when the query parser
  extracted a structured filter.
- **Fuzzy trigram fallback** — only engages when FTS produced zero
  hits.

---

## Flow

```
POST /search { query, filters, limit }
    │
    ▼
SearchService.search (services/search_service.py:105)
    │
    │  empty query? → [], 0ms
    │
    │  1. PARSE
    │     parsed = query_parser.parse(query)    (F89.a)
    │     fill Nones in caller filters with parsed ones
    │     (explicit > implicit; skills only promoted alongside
    │      a strong filter)
    │
    │  2. OWNER SCOPE
    │     owner_filter = None if actor.role == ADMIN else actor.id
    │
    │  3. VECTOR
    │     _vector_search(query, document_type, limit*3, owner_id)
    │       Chroma query with where { owner_id, document_type }
    │       drop hits with distance > threshold (F80 + F85.d)
    │     _drop_orphan_vector_hits   (F86.c; scan Postgres for hydration)
    │
    │  4. SQL METADATA  (only if has_structured_filter)
    │     documents.search_by_metadata(...)
    │       JSONB `@>` containment on skills (F89.a.1)
    │       jsonb_typeof guard on experience_years (F89.a.1)
    │       date_from / date_to on created_at
    │
    │  5. LEXICAL FTS
    │     lexical_query = expand_acronyms(normalize_tech_tokens(query))
    │     documents.full_text_search(lexical_query, ...)
    │
    │  6. FUZZY (only if FTS returned zero)
    │     documents.fuzzy_search(query, ...)
    │
    │  7. MERGE
    │     merge_limit = max(reranker_top_k, limit) if reranker else limit
    │     merged = _rrf_merge(vector, sql, lexical, merge_limit,
    │                         w_vector, w_sql, w_lexical=2.0)
    │
    │  8. HYDRATE
    │     docs_map = documents.get_many(merged doc_ids)
    │
    │  9. HIGHLIGHT
    │     terms = extract_query_terms(query)   (services/highlight.py:84)
    │     for each highlight: match_spans = find_match_spans(text, terms)
    │
    │ 10. STATUS FILTER
    │     skip doc if doc.status != READY  (F86.b mirror)
    │
    │ 11. RERANK  (if reranker wired and results non-empty)
    │     _rerank_results(query, results, limit)
    │       cross-encoder over top-K → top-limit
    │     else results[:limit]
    │
    ▼
(results, elapsed_ms)
```

---

## Weighted RRF (`_rrf_merge`)

Reciprocal Rank Fusion (k=60), each source weighted:

```
score(doc) = Σ w_source / (RRF_K + rank_in_source + 1)
```

| Source | Default weight | Setting |
|--------|----------------|---------|
| Vector | 1.0 | `rrf_weight_vector` |
| SQL metadata | 1.0 | `rrf_weight_sql` |
| Lexical FTS | **2.0** | `rrf_weight_lexical` |

Lexical is biased up (F85.c) so F87's filename-A / skills-B weighting
carries through to the merged ranking. Without the bias, vector
tended to drown out exact filename matches on short corpora.

RRF collapses heterogeneous score scales (ts_rank_cd vs cosine
distance) to ranks. Raw scores never normalize; the merged score is
reported as-is for debugging but the UI just uses the confidence
band.

---

## Confidence band

`_confidence_band` (`search_service.py:902`) classifies the merged
score:

| Band | Threshold |
|------|-----------|
| `high` | ≥ `search_confidence_high` |
| `medium` | ≥ `search_confidence_medium` |
| `low` | otherwise |

Operator-visible knobs so a corpus-specific calibration is possible.
Frontend shows this as a colored chip next to the result.

---

## Highlights

`services/highlight.py`:

- `extract_query_terms` — tokenize query, drop stopwords, keep tech
  tokens (`c++`, `.net`, `node.js`).
- `find_match_spans` — `(start, end)` byte offsets per term in
  snippet text. Word-boundary regex for alphanumeric terms; plain
  substring for tech tokens.
- Overlaps merged.

Returned as `match_spans` inside each highlight. The frontend's
`<HighlightedText>` wraps spans in `<mark>` (F92.1) — no HTML
travels on the wire, so XSS surface is closed.

---

## Reranker (optional)

When `_reranker` is non-null (default `local` cross-encoder):

- Input: `merge_limit = max(reranker_top_k, limit)` candidates
  — currently 20 (`settings.reranker_top_k`).
- The reranker reads `(query, top-1-highlight-text)` per doc.
- Output: top `limit` docs in new order.
- Fallback: on any reranker exception, keep RRF order.

See `07-reranker.md` for the full cross-encoder flow.

---

## RAG-side retrieval lanes (not `/search`)

`SearchService` also serves the RAG pipeline, which uses two extra
entry points that `POST /search` never touches:

- **`retrieve_chunks`** (`search_service.py:280`) — chunk-level
  hybrid retrieval. Same four-signal framing as `search`, but emits
  `RetrievedChunk` objects. Since F103.c each chunk is also hydrated
  with its **author** (`authored_by_id` / `authored_by_name`) via two
  batched repo lookups — `find_candidates_by_ids` for the explicit FK
  and `find_resume_authors` as the resume self-link fallback
  (`search_service.py:372-420`).
- **`retrieve_candidate_summaries`** (`search_service.py:426`) —
  F104.a candidate-summary lane. Queries a separate Chroma collection
  (the `_candidate_summary_store` constructor arg,
  `search_service.py:95`) of one-line recruiter briefs, owner-scoped,
  distance-cut by `rag_candidate_max_distance`. RAG-only — not part
  of the `/search` four signals.

See `08-rag-pipeline.md` for how RAG consumes both.

---

## Configuration knobs

| Setting | Default | Effect |
|---|---|---|
| `search_max_distance` | `None` | Override embedder's per-model threshold. |
| `search_max_highlights_per_doc` | 3 | Cap on snippets per result. |
| `search_confidence_high` / `_medium` | corpus-tuned | Band thresholds. |
| `rrf_weight_vector` | 1.0 | RRF multiplier on vector rank. |
| `rrf_weight_sql` | 1.0 | RRF multiplier on SQL-metadata rank. |
| `rrf_weight_lexical` | 2.0 | RRF multiplier on FTS rank (F85.c). |
| `reranker_top_k` | 20 | Candidates fed to the reranker. |

---

## Known issues / pain points

1. **Highlights per hit don't always capture the matched term.**
   `highlights` come from the top-1 vector chunk per doc. If the
   match was lexical (FTS filename hit), the best highlight might
   be an unrelated body chunk. Works well in practice because
   lexical-boosted docs usually also have a decent vector chunk;
   fails on filename-only matches (a resume indexed but no chunk
   matches the query token).
2. **Merged score opacity.** `confidence` is derived from a raw RRF
   score that sums weights across multiple sources. A high-vector-
   no-FTS doc and a no-vector-but-FTS-matches doc may both land at
   `medium`, which isn't meaningful to users.
3. **Vector hits contribute only top-1 highlight per doc to the
   reranker input.** If a doc's best signal is chunk #3 (buried),
   the reranker sees chunk #0. Not awful — the ranker tends to
   correct — but leaves points on the table.
4. **No pagination (`offset` missing).** `SearchRequest` has
   `limit` only. Scoped in F89.
5. **Fuzzy fires only on zero FTS hits** — an FTS query that returns
   garbage (all low-rank matches on an unrelated word) never
   triggers fuzzy. Threshold-gated fuzzy would help.
6. **Distance threshold lives on the embedder + settings override;
   fuzzy threshold lives as a constant.** Inconsistent lever locations
   make tuning awkward.
7. **`search_by_metadata` ignores the query string.** If both
   a structured filter *and* a query string are provided, only the
   vector + lexical paths see the string — SQL returns filter-matching
   docs ordered by recency, not relevance. The filter still narrows
   through RRF merging, but the SQL ranking position is essentially
   noise.
8. **`document_type` parsed from the query is a STRING, converted at
   the boundary.** `_document_type_from_str` silently returns `None`
   for unknown values (`services/search_service.py:888`). A malformed
   parser extension would leave the type filter unapplied without
   error.
9. **Highlight tokenizer doesn't see the normalized form.** User
   types `C++` → lexical path sees `cpp`, but highlight sees `c++`.
   Works today because index + query both carry raw + normalized;
   the divergence only bites if we ever highlight from normalized
   text.
10. **Orphan-drop runs after vector retrieval, not before ranking.**
    We pay Chroma for N*3 hits then filter; orphans inflate
    `n_results` budget. Low-impact until corpus has many deleted
    docs.
11. **Per-doc result shape is a dict.** `SearchResult` dataclass
    exists, but the final results list from `search()` is
    `list[dict]`. Losing a typing boundary inside the service makes
    refactors slightly heavier. Pydantic schemas at the edge do the
    real contract work so this is cosmetic.

---

## Improvement opportunities

### Short-term

- **Pagination.** Add `offset` to `SearchRequest` and thread through
  to every retrieval path. Easy; high-value once the corpus grows.
- **Per-doc highlight picked by source.** If the top signal was
  lexical, use the snippet around the best FTS term match
  (`ts_headline` can give us this directly) rather than the top
  vector chunk.
- **Threshold-gated fuzzy.** Trigger fuzzy when FTS max rank is
  below a floor (e.g. 0.05), not just zero. Catches weak-FTS
  queries.
- **Recency tie-break in RRF.** Pre-sort equal-score docs by
  `created_at desc` before truncation. Matches Slack / Linear
  defaults and stops result flicker.

### Medium-term

- **Relevance telemetry.** For each query, log which source fed the
  top-K docs (vector / SQL / lexical / fuzzy). One dashboard → know
  where ranking is actually coming from; catches regressions.
- **Per-signal confidence.** Attach `{"source": "lexical",
  "source_rank": 1}` to each result so the frontend can explain
  *why* a doc ranked.
- **Tighter snippet selection.** Pick the chunk maximizing
  `query_terms ∩ chunk_terms` rather than top-1 retrieved.
- **MMR diversity pass** after RRF to limit per-doc dominance in
  chunk-level RAG retrieval (doesn't apply to doc-level search).
  Low priority until the corpus has many near-duplicate docs.
- **Skill canonicalization** shared with candidate matching (F83).
  Feeds both the parser vocab and the JSONB filter so "JS" and
  "JavaScript" unify end-to-end.

### Long-term

- **Learning-to-rank over merged candidates.** Feature inputs:
  RRF components, reranker score, recency, owner-specific
  interaction priors. Pay off once traffic justifies offline
  training.
- **Query plan explanation.** `?explain=true` returns a structured
  breakdown — parsed filters, normalized lexical query, vector
  distance per retained hit, RRF decomposition, reranker scores.
  Serious debugging aid; moderate implementation cost.
- **Two-stage retrieval for large corpora.** Today everything
  runs per-request; at 10M+ chunks, a cheap pre-filter (title +
  metadata FTS) feeding the vector path would cut Chroma load.

---

## Cross-references

- **Code**: `backend/app/services/search_service.py`,
  `app/services/highlight.py`,
  `app/api/routes/search.py`,
  `app/schemas/search.py`.
- **Upstream**: `04-lexical-and-fuzzy-index.md`,
  `05-query-understanding.md`, `03-embeddings-and-vector-store.md`.
- **Downstream**: `07-reranker.md`, `08-rag-pipeline.md` (shares
  retrieval via `ChunkRetriever`).
- **Design**: `docs/architecture.md` §8,
  `docs/search-hardening.md`, `docs/rag-pipeline.md` §2,
  `docs/features.md` F80, F85.c, F86, F87, F89.
- **Eval**: `tests/eval/test_search_quality.py`,
  `tests/eval/baseline.json` (P@5 0.252 · R@5 1.000 · MRR 0.859
  on the 7-doc fixture).
