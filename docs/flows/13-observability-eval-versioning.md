# 13 · Observability, eval & versioning

Where we look when something regresses, how we measure whether a
retrieval / classification / intent change actually helped, and how
we stay in sync when the chunker or embedder changes.

---

## Purpose

Give engineers + ops a single place to understand:

- What signals each component emits into logs.
- How the eval harnesses work and what each protects.
- How the version stamps on documents gate the re-index flows.
- What scripts exist for recovery / reindex.

---

## Observability — per-component log lines

### Extraction / indexing (worker)

One line per processed document:

```
document <uuid> processed: type=resume, 4212 chars
```

Chunk-level:

```
indexed document <uuid> (14 chunks, 14 contextualized, context_version=v2, chunking=v3-heading-as-metadata)
```

Errors from indexing are caught in `ExtractionService._index`
(`extraction_service.py:164`) and logged but non-fatal:

```
embedding indexing failed for document <uuid>
<stack trace>
```

### Search

Nothing structured today — `SearchService` returns `elapsed_ms` on
the wire; there's no per-query log line inside the service itself.
Timing lives in the response, per-source breakdown lives nowhere.

### RAG (`rag_service._build_context`)

Single grep-able line per answered query:

```
rag context: 5/5 chunks kept, ~1247 tokens
   (cutoff=none, budget=4000)
   | intent=comparison conf=0.87 runner=ranking
   prompt=v5 system_prompt_chars=1892
```

| Field | Signal |
|---|---|
| `kept/total chunks` | F81.b + F81.c gate effectiveness |
| `~tokens` | F81.c budget consumption |
| `cutoff=` | F81.b applied distance threshold |
| `budget=` | F81.c configured budget |
| `intent=` | F81.g classifier output |
| `conf=` | F81.g confidence |
| `runner=` | F81.g second-best intent (ambiguity signal) |
| `prompt=` | `PROMPT_VERSION` for A/B correlation |
| `system_prompt_chars=` | Guards against prompt bloat |

**Dev visibility**: `_configure_dev_logging()` (`app/main.py:20`)
runs `logging.basicConfig(level=INFO)` behind `settings.debug` and is
called from `create_app()`, so `app.*` INFO lines surface in dev
without extra flags. `basicConfig` is a no-op once the root logger
has handlers, so uvicorn reload and pytest stay unaffected. Prod
configures logging externally.

### ChromaDB startup integrity

`ChromaVectorStore._log_startup_integrity` (`chroma_store.py:131`):

```
ChromaVectorStore ready: collection=documents_bge_small_en_v1_5
                         model=BAAI/bge-small-en-v1.5 chunks=142
                         whole-doc-collection=documents_whole_bge_small_en_v1_5
                         documents=37
```

With a drift warning if the collection's stored `embedding_model`
disagrees with the configured one.

### Gmail sync

Per-connection per-run:

```
gmail sync complete for alice@example.com:
  scanned=34 ingested=12 dedup=20 no_attachment=1
  errors=1 error_types=HTTPError:1
```

Activity-log entry written too (`ActivityAction.GMAIL_SYNC_RUN`).

### LLM adapters (F81.i)

Expected / known error types log WARN without a stack:

```
WARN LLM provider error (llm_rate_limited): ...
```

Unknown / unexpected exceptions log `exception` (stack trace):

```
EXCEPTION Unexpected LLM stream failure
<full traceback>
```

---

## Eval harnesses

### Search quality — `tests/eval/test_search_quality.py`

- **Fixture corpus**: 7-8 curated docs covering resume / report /
  contract / letter types.
- **Golden queries**: `tests/eval/dataset.py` has the set;
  `baseline.json` stores last-measured per-query results.
- **Metrics**: P@5, R@5, MRR overall + per bucket
  (`role_skill`, `doc_type`, `negative`, `filtered`, `edge`,
  `filename`, `acronym`, `typo`).
- **Baseline today**: P@5 0.252 · R@5 1.000 · MRR 0.790
  (`tests/eval/baseline.json`).
- **Run**: `make eval` (shell wrapper around `pytest` with the
  real DB + Chroma).

### Intent accuracy — `tests/eval/test_intent_accuracy.py`

- **Fixture**: `tests/eval/intent_queries.json` — 63 labeled queries
  covering every intent.
- **Metric**: overall accuracy + per-intent scorecard +
  misclassifications.
- **Gate**: `INTENT_ACCURACY_THRESHOLD = 0.80`. Below → CI fails.
- **Current**: 93.7% overall, 100% on every specific intent
  (misses are `general` queries bleeding into nearby intents).
- **Run**: `make eval-intent`.

### Query parser accuracy — `tests/eval/test_query_parser_accuracy.py`

- **Fixture**: `tests/eval/query_parser_cases.json` — 58 labeled
  cases per field (years, skills, doctype, dates).
- **Metric**: per-field F1 (precision + recall against labeled
  extractions).
- **Gate**: `QUERY_PARSER_F1_THRESHOLD = 0.85`. Below → CI fails.
- **Current**: 100% F1 across every field.
- **Run**: `make eval-parser`.

### Skill extraction — `tests/eval/test_skill_extraction_accuracy.py`

- **Fixture**: `tests/eval/skill_extraction_cases.json` — 8 labeled
  resume bodies with `expected_skills`.
- **Metric**: per-fixture recall + overall micro-recall (recall, not
  F1 — LLM false positives are tolerable downstream).
- **Gate**: `LLM_SKILL_RECALL_THRESHOLD = 0.80`. Skipped when no LLM
  provider is configured (prompt-regression guard, not hard CI).
- **Run**: `make eval-skill-extraction`.

### RAG answer quality — `tests/eval/test_rag_answer_quality.py`

- **Fixture**: `tests/eval/rag_answer_cases.json` — 7 labeled
  `(question, chunks, expected-properties)` fixtures with
  must-include / must-not-include substring rules.
- **Metric**: per-fixture pass/fail (a fixture passes iff every
  assertion holds); the eval passes iff the pass rate clears
  `RAG_ANSWER_FIXTURE_PASS_THRESHOLD = 0.80`.
- **Gate**: skipped when no LLM provider is configured.
- **Run**: `make eval-rag-answer`.

### Unit / integration tests

- `tests/test_chunking.py` — chunker rules against element
  fixtures.
- `tests/test_chunk_retrieval.py` — RAG retrieval end-to-end with
  real DB + Chroma.
- `tests/test_rag_streaming.py` — SSE framing + event sequence.
- `tests/test_document_fts.py` — SQL normalize_tech_tokens ↔
  Python normalize_tech_tokens drift check.
- `tests/test_search_relevance.py` — individual SearchService
  assertions (RRF weights, orphan drop, owner scoping).
- `tests/test_cross_encoder_reranker.py` — reranker behaviour +
  fallback.
- `tests/test_gmail_sync.py` — claim / retry / dedup invariants.
- `tests/test_llm_error_translation.py` — F81.i translator
  coverage.
- `tests/test_encryption.py` — F73 envelope encryption.

`tests/conftest.py` provisions a real Postgres + Redis via Docker
(no mocks).

---

## Versioning + re-index flows

### Version stamps on documents

| Column | Bumped when | Current |
|---|---|---|
| `extraction_version` | Extractor or output shape changes. | `v2-unstructured` |
| `chunking_version` | Chunker rules change. | `v3-heading-as-metadata` |
| `embedding_model_version` | Embedder model swap. | `BAAI/bge-small-en-v1.5` (free-form) |

Chunk-level metadata also carries `chunking_version` so retrieval can
detect mixed-version corpora (we don't actively do this today — just
the logs on startup flag drift).

### Scripts

| Script | What it does | When to run |
|---|---|---|
| `scripts/reindex_embeddings.py` | Re-embed from persisted `document_elements`. Skips extraction. | After `EMBEDDING_MODEL` or `CONTEXTUALIZATION_VERSION` change. |
| `scripts/reextract_all.py` | Flip all non-pending docs to PENDING; re-enqueue `extract_document_text`. | After `CHUNKING_VERSION` or `EXTRACTION_VERSION` bump. |
| `scripts/reclassify_documents.py` | Re-run the classifier over existing docs. | After a classifier prompt / keyword change. |
| `scripts/relink_authors.py` | Re-resolve document → candidate author links. | After an authoring-heuristic change. |
| `scripts/backfill_candidate_names.py` | Backfill candidate display names. | One-off data repair. |
| `scripts/backfill_candidate_summaries.py` | Backfill candidate one-liner summaries. | After the F104.a summary feature landed. |
| `scripts/prepare_viewables.py` | Generate viewable renditions for stored documents. | One-off backfill. |
| `scripts/nuke_documents.py` | Wipe all documents + their vectors. | Destructive reset (dev only). |
| `scripts/create_admin.py` | Seed admin user. | Fresh install. |
| `scripts/export_openapi.py` | Dump OpenAPI spec for frontend SDK generation. | CI or manual pre-commit. |

Make targets (`Makefile`):

```
make eval                  # search quality
make eval-intent           # intent classifier
make eval-parser           # query parser
make eval-skill-extraction # LLM skill-extraction recall
make eval-rag-answer       # RAG answer quality
make tilt                  # full dev stack (infra + api + worker + web)
make api / worker / web    # single dev process, foreground
make setup                 # first-run bootstrap
```

---

## Known issues / pain points

1. **No structured search-service log line.** We log
   `"indexed document X"` on ingest but nothing on query. Harder
   to diagnose "why did this query return empty" after the fact.
2. **Timing not broken out per step.** Extract / classify /
   contextualize / embed timings are invisible. Bottleneck
   isolation depends on wall-clock guessing.
3. **Eval baseline is JSON-on-disk.** Any eval run that differs
   overwrites `baseline.json`. A CI check that diffs but doesn't
   auto-update would be safer (currently we rely on code review
   catching regressions).
4. **No A/B infrastructure.** We can swap `PROMPT_VERSION` or
   `EMBEDDING_MODEL`, but we can't run two in parallel to
   measure.
5. **Version stamps don't cover classifier or contextualizer
   prompts.** A classifier keyword change can silently change
   retrieval quality; nothing marks affected docs as "needs
   re-classify."
6. **Stale-version sweep isn't scripted.** A per-doc targeted
   re-embed exists (`reembed_document` task), but there's no
   script that finds *only* docs on a stale
   `embedding_model_version` / `contextualization_version` and
   re-embeds them — `reindex_embeddings.py` still rebuilds
   everything. Model A/B cost scales with corpus size.
7. **Activity log doesn't capture RAG or search events.** Only
   document / job / gmail events. Query history isn't auditable.
8. **No latency SLOs encoded anywhere.** Ops has no authoritative
   "what should P95 latency be" for search or RAG.
9. **Per-query observability line is a single string.** A
   structured log (JSON) would be much easier to pipe into a
   dashboard.

---

## Improvement opportunities

### Short-term

- **Per-step timing in extraction.** Wrap `_extract`, `_classify`,
  `_index` with a tiny `@timed` decorator that logs ms + doc_id.
- **Search-service per-query log.** One line: query hash, k per
  source (vector/SQL/lexical/fuzzy), merged-k, reranked-k,
  elapsed. Matches RAG's observability shape.
- **Stale-version re-embed sweep.** A script that queries
  `documents where embedding_model_version != current` (or stale
  `contextualization_version`) and enqueues `reembed_document` per
  doc — the per-doc task already exists, only the corpus-wide sweep
  is missing.
- **JSON-structured observability lines.** Swap the string format
  for `logger.info("rag_context", extra={...})` so log aggregators
  can parse fields without regex.

### Medium-term

- **Eval baseline in CI.** Job that runs `make eval eval-intent
  eval-parser`, compares to a committed `baseline.json`, fails the
  PR on regression beyond a tolerance. Today it's manual.
- **Query-activity log.** Light-weight table
  `query_logs(actor_id, query, kind='search'|'rag', elapsed_ms,
  source_breakdown, intent, created_at)`. Feeds dashboards +
  audit.
- **RAG end-to-end eval — deepen it.** `test_rag_answer_quality.py`
  already exercises the real LLM with substring must/must-not rules
  (see "What changed"). The next step is semantic-similarity
  scoring against golden answers rather than brittle substrings.
- **Prompt version hash.** Auto-compute `PROMPT_VERSION` as a
  hash of the concatenated prompt layers. Eliminates the manual
  version bump.
- **Classifier + contextualizer version stamps.** Columns on
  `documents` like the extraction stamps; drives a targeted
  reclassify / re-contextualize script.

### Long-term

- **Full telemetry pipeline** (OpenTelemetry traces + metrics).
  Per-request trace covering upload → worker → Chroma → answer.
  Requires OTEL-instrumented FastAPI + Celery.
- **Golden-corpus expansion.** The 7-doc fixture is hitting
  retrieval ceiling. Need a 50+ doc multi-type corpus with
  overlapping vocabulary to differentiate between models,
  thresholds, and ranker choices.
- **A/B harness.** Route X% of traffic to a second
  configuration (`EMBEDDING_MODEL=alt`, `PROMPT_VERSION=v3`) and
  compare metrics. Without this, every "we think this helps"
  claim stays a vibe.
- **SLOs + alerts.** Latency + error-rate SLOs per endpoint,
  measured against recent baseline. Alerts on deviation, not on
  absolute.
- **Automated recovery flows.** Instead of telling operators to
  run a script, a FAILED doc surfaces a "re-process" action,
  stale-claim Gmail messages auto-recover, model drift triggers
  a background re-embed.

---

## Cross-references

- **Code**: `backend/app/main.py` (`_configure_dev_logging`),
  `backend/app/services/rag_service.py` (RAG log),
  `app/adapters/chroma_store.py` (Chroma integrity log),
  `app/services/gmail_sync_service.py` (Gmail sync log),
  `app/services/reembed_service.py` + `app/worker/tasks.py`
  (`reembed_document`), `backend/tests/eval/` (harnesses +
  fixtures), `backend/scripts/` (reindex / reextract / reclassify /
  backfills / admin / openapi).
- **Design**: `docs/features.md` F80 (eval), F81.b/c/g (rag
  observability), F85.f (embedding versioning), F86.b (status
  filter), F92.1 (highlights), F103.b/d/e (skill / answer evals,
  contextualization versioning).
- **Flows**: every flow doc has a "Configuration knobs" + "Known
  issues" section that pairs with this one.

---

## What changed

- **F63 — dev logging shipped.** `_configure_dev_logging()` in
  `app/main.py` runs `logging.basicConfig(level=INFO)` behind
  `settings.debug` and is invoked from `create_app()`, so `app.*`
  INFO lines (including the RAG observability line) surface in dev
  with no extra uvicorn flags.
- **F103.b / F103.e — eval harnesses shipped.**
  `test_skill_extraction_accuracy.py` (LLM skill recall) and
  `test_rag_answer_quality.py` (RAG answer must/must-not rules)
  joined the harness set, with `make eval-skill-extraction` and
  `make eval-rag-answer` targets.
- **F103.c — targeted re-embed shipped.** A `reembed_document`
  Celery task (`app/worker/tasks.py`) backed by
  `app/services/reembed_service.py` re-embeds a single document;
  a corpus-wide stale-version sweep is still a follow-up.
