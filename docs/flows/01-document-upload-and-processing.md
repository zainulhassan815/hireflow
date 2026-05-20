# 01 · Document upload & processing

The ingestion path: from `POST /documents` through Celery to a `READY`
document with extracted text, elements, classification, indexed chunks,
and (for resumes) an auto-created candidate.

---

## Purpose

Turn a user-supplied file into everything downstream needs:

- Canonical text (Postgres `documents.extracted_text`).
- Typed layout regions (Postgres `document_elements`) — cached so
  re-chunking doesn't re-extract.
- Document type + metadata (`document_type`, `metadata_.skills`,
  `experience_years`, `education`, emails, phones).
- Weighted FTS index (`documents.search_tsv` generated column — fires
  on write, no Python).
- Vector chunks in ChromaDB (one collection per embedding model).
- For resumes: a `Candidate` row linked via
  `candidates.source_document_id`.

Everything is out-of-band: the HTTP handler returns `201` with
`status=PENDING` instantly, a Celery task does the work, a follow-up
`GET /documents/{id}` shows `READY`.

---

## Flow

```
POST /documents  (routes/documents.py)
   │  multipart: file + mime + filename
   │  DocumentService.upload (services/document_service.py:53)
   │    - MIME allowlist (ALLOWED_MIME_TYPES at :20)
   │    - Size cap (MAX_FILE_SIZE_MB → FileTooLarge)
   │    - Put blob  → MinIO at key `{owner_id}/{uuid}/{filename}`
   │    - Insert `documents` row, status=PENDING
   ▼
201 with document.id   ─────────┐
                                │
                                │  route also enqueues
                                ▼
                      extract_document_text.delay(document.id)
                      (worker/tasks.py:24)
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│ Celery worker — sync session, its own asyncio loop per task  │
│ ExtractionService.process (services/extraction_service.py:55)│
│                                                              │
│ Task wiring (worker/tasks.py:31) — before process():         │
│   - Build embedder + ChromaVectorStore + EmbeddingService    │
│   - Build an LLM callable (llm_call) from llm_provider        │
│     (anthropic/ollama) for the F104.a candidate-summary path │
│   - SyncCandidateService(session, llm_call=…,                │
│       candidate_embedder=embedder, candidate_store=store)    │
│   - Chain on_ready = SyncCandidate → AuthorLinkage (:137)    │
│                                                              │
│ 1. status PENDING → PROCESSING, commit                       │
│ 2. _extract    (:94)                                         │
│    - storage_get(key)  → bytes                               │
│    - CompositeExtractor.extract(data, mime_type)             │
│         └─ UnstructuredExtractor                             │
│              partition_pdf / partition_docx                  │
│              returns ExtractionResult(text, pages, elements) │
│         └─ ImageExtractor → VisionProvider.extract_text…     │
│    - doc.extracted_text = result.text                        │
│    - doc.extraction_version = "v2-unstructured"              │
│    - Persist elements (delete-then-insert) in                │
│      document_elements (:103)                                │
│ 3. _classify  (:127)                                         │
│    - CompositeClassifier.classify(text, filename)            │
│         └─ RuleBasedClassifier (keyword density + filename)  │
│         └─ (if conf < 0.4) LLM fallback                      │
│    - Sets doc.document_type                                  │
│    - Merges classifier metadata into doc.metadata_           │
│ 4. _index  (:147)                                            │
│    - chunk_elements(doc.elements)  → list[Chunk]             │
│    - ChunkContextualizer.contextualize(doc, chunks) (F82.c)  │
│    - EmbeddingService.index_document(doc, chunks=chunks)     │
│         └─ ChromaVectorStore.upsert (with embedder)          │
│    - doc.chunking_version = "v3-heading-as-metadata"         │
│    - doc.embedding_model_version = embedder.model_name       │
│                                                              │
│ 5. status → READY, commit                                    │
│    (indexing failure is non-fatal — logged, doc still READY) │
│                                                              │
│ 6. on_ready chain (post-commit, extraction_service.py:91)    │
│    └─ SyncCandidateService.handle_document_ready (:58)       │
│         if doc.document_type == RESUME:                      │
│           create-or-update Candidate from metadata, then     │
│           CandidateSummaryService builds a recruiter brief   │
│           via llm_call and indexes it into the               │
│           candidates_<slug> Chroma collection (F104.a)       │
│    └─ AuthorLinkageService.handle_document_ready             │
│         backfill candidate→document FK by matched email      │
│                                                              │
│ 7. ViewerPreparationService.prepare (tasks.py:166)           │
│    - Runs after the task returns, on its own fresh session   │
│    - Builds the viewer asset (PDF render etc.); a failure    │
│      can't reverse the committed READY state (F105.b)        │
└──────────────────────────────────────────────────────────────┘
```

Side effects written throughout the flow:

- Postgres `documents` row (status transitions, version stamps).
- Postgres `document_elements` rows (CASCADE from `documents`).
- Postgres `documents.search_tsv` — regenerated automatically by the
  `normalize_tech_tokens(...)` generated column on every write.
- ChromaDB `documents_<model_slug>` collection — one row per chunk.
- ChromaDB `candidates_<model_slug>` collection — one recruiter-brief
  vector per resume (F104.a).
- Postgres `candidates` row (only for resumes).

---

## Key invariants

- **`status=PENDING` is the only state the worker will pick up.**
  `extraction_service.py:64` short-circuits on anything else. If a
  reprocessing job is needed, the caller must flip the row back to
  PENDING (see `scripts/reextract_all.py`).
- **Element persistence happens before classification.** `_persist_elements`
  deletes-then-inserts so a re-extraction's element set can change
  wholesale without merge logic. Means a worker crash between
  `_persist_elements` and `_classify` leaves elements but no
  classification — fine, the next run re-extracts atop.
- **Indexing failure is intentionally non-fatal.** A failed embed
  still lets the doc reach READY so the browser doesn't stay stuck at
  PROCESSING forever. The `indexing failed for document …` WARN in
  logs is the signal to re-run `scripts/reindex_embeddings.py`.
- **`on_ready` fires only on success.** The chained hooks
  (auto-candidate creation, candidate-summary indexing, author
  linkage) will not run if the document ends at FAILED. Each hook
  swallows its own exceptions, so a failure in one never rolls back
  extraction or blocks the next hook.
- **The worker uses a sync DB session** (`get_sync_db`), not the
  async one used by routes. Mixing session types has bitten us
  before — keep it sync inside the task.

---

## Configuration knobs

| Setting | Default | Effect |
|---------|---------|--------|
| `MAX_FILE_SIZE_MB` | 10 | Upload cap; Gmail sync honours the same. |
| `STORAGE_*` | local MinIO | Blob storage endpoint + credentials. |
| `EXTRACTION_STRATEGY` | `hi_res` | `fast` for CPU, `hi_res` for GPU layout + tables. |
| `EXTRACTION_INFER_TABLES` | `true` | Turn off to skip table transformer load. |
| `VISION_PROVIDER` | `tesseract` | `claude` / `ollama` / `tesseract` / `none`. Only used by raw-image uploads. |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Picks Chroma collection + distance threshold. |
| `LLM_PROVIDER` / `LLM_MODEL` | Anthropic + Haiku | Backs the classifier LLM fallback and the chunk contextualizer. |
| `CONTEXTUALIZER_MODE` | `auto` | `summary` / `full_doc` / `auto`. Picks F82.c mode per doc. |

All live in `backend/app/core/config.py`.

---

## Known issues / pain points

1. **Orphan chunks vs demoted docs.** A doc that re-enters PROCESSING
   after being READY keeps its old Chroma chunks. Search guards against
   this at retrieval time (`SearchService._drop_orphan_vector_hits` at
   `search_service.py:735`), but a tighter fix is "don't index chunks
   for non-READY docs at all." See
   `docs/search-hardening.md` §3 / F86.c.

2. **Classification metadata collisions.** `_classify` merges the
   classifier's `metadata` into `doc.metadata_` with
   `classification_confidence` appended. Nothing explicitly namespaces
   classifier fields; if a future classifier emits a `skills` key
   with a different shape (e.g. list of objects vs list of strings),
   downstream consumers (JSONB containment in `document_repo.search_by_metadata`
   at `repositories/document.py:84`, auto-candidate at
   `sync_candidate_service.py:74`) will quietly drift.

3. **Extraction timing is not observable per-document.** We log
   "document X processed" at the end but don't break out extract /
   classify / index timing. Makes it hard to tell whether hi_res
   model load dominates vs Chroma upsert vs Haiku contextualizer.

4. **`hi_res` model load is first-request latency.** 5-30s on the
   first PDF. Not pre-warmed; if Celery restarts, the next doc pays
   the cost. Visible as a long PENDING → READY flight.

5. **Classifier LLM fallback is silent on errors.** `CompositeClassifier`
   falls through to the primary result if the LLM call fails. Fine for
   reliability; bad for observability — we never know how often the
   fallback is actually getting invoked / failing.

6. **Status enums aren't modelled as a state machine.** Nothing
   prevents a direct PROCESSING→PENDING flip from outside
   `ExtractionService`. The re-extraction script does this deliberately,
   but a bug elsewhere could too.

7. **No dead-letter handling.** After 3 Celery retries, a failed doc
   stays at FAILED with the last exception in the worker log —
   nothing in Postgres records *why*. Users see "failed" but can't
   self-serve.

8. **`metadata.skills` from the rule-based classifier is lowercase,
   but there's no contract enforced at the boundary.** Search code
   normalizes again (`repositories/document.py:134`); safe today but
   will drift the moment a new metadata writer lands.

9. **Auto-candidate update is merge-biased: never clears.** `_create_or_update`
   at `sync_candidate_service.py:74` overwrites fields when the fresh
   extract has them but never nulls them. Re-extracting a resume with
   new metadata that lost a phone number silently keeps the old one.

10. **`extracted_text` is joined from elements with `\n\n`.** Good
    enough for FTS but loses column/reading-order nuance for
    multi-column PDFs. Downstream RAG chunks see the same join, which
    is fine because element-aware chunking handles structure; FTS
    consumers see text that's slightly less faithful than the doc.

---

## Improvement opportunities

### Short-term (≤1 week)

- **Block chunk indexing on non-READY.** Check `doc.status ==
  DocumentStatus.READY` before `EmbeddingService.index_document` fires,
  or stamp chunks with `owner_id + status` and have Chroma `where`
  clause filter at retrieval. Would collapse the orphan + stale-chunk
  edge into a single guard rather than three workarounds in
  `SearchService`.
- **Structured timing log** per pipeline step
  (`extract_ms`, `classify_ms`, `contextualize_ms`, `embed_ms`,
  `chunks_indexed`). One JSON-ish line per doc makes dashboards
  trivial and catches regressions (today we only get end-to-end).
- **Record failure reason on FAILED docs** — add
  `documents.last_error_summary` (text, truncated, no stack) and surface
  on `GET /documents/{id}`. Users can then re-upload or report.
- **Namespace classifier metadata** under
  `metadata.classifier.skills` etc. so a newer classifier (F84) can
  emit into a separate subkey and be A/B'd against the old.
- **Pre-warm the hi_res model** on worker startup if
  `EXTRACTION_STRATEGY=hi_res`. One call to `partition_pdf` on a
  dummy PDF would eat the cost before the first real upload.

### Medium-term

- **Formal state machine for `DocumentStatus`** with explicit
  allowed transitions (a `set_status` helper that raises on
  illegal moves). Prevents accidental skips and documents what
  scripts like `reextract_all.py` are actually doing.
- **Dead-letter queue** for docs that exhaust Celery retries.
  Surface a "retry" action in the UI that flips the row back to
  PENDING.
- **Chunking re-run without re-extract**. Today we have
  `scripts/reindex_embeddings.py` for embedder swaps and
  `scripts/reextract_all.py` for full rebuild. A middle path —
  "re-chunk from persisted `document_elements`" — would unlock
  F82.f (multi-granularity chunks) without paying the
  extraction cost again. The code path already exists inside
  `EmbeddingService.index_document` when called with `elements=`;
  wiring a dedicated script is straightforward.
- **Targeted re-embed**: query `documents` where
  `embedding_model_version != settings.embedding_model`, iterate.
  Today `reindex_embeddings.py` rebuilds all. Targeted cuts
  reindex cost materially after a model swap in a mixed corpus.
- **Observable classifier fallback**. INFO counter
  "rule-based / LLM / final" so we can graph how often the
  LLM is deciding.

### Long-term

- **Structured ingestion events** published onto a Redis/Postgres
  stream — `DocumentExtracted`, `DocumentClassified`,
  `ChunksIndexed`, `CandidateCreated`. Any future integration
  (webhooks, audit, search index rebuild triggers) consumes the
  stream instead of polling.
- **Per-document confidence pipeline**. Classification already
  emits a confidence; extraction, chunking, and indexing could
  too. A composite "ingestion confidence" would let us flag
  docs that are "ready but suspect" for human review.
- **Layout-aware extraction feedback loop**. When a user corrects
  a classified type, we currently ignore it. F84 has an entry
  for this; long-term pairs well with retraining the rule-based
  classifier or fine-tuning a small local classifier per tenant.

---

## Cross-references

- **Where the code lives**: `backend/app/api/routes/documents.py`,
  `app/services/document_service.py`,
  `app/worker/tasks.py::extract_document_text`,
  `app/services/extraction_service.py`,
  `app/adapters/text_extractors.py`,
  `app/adapters/classifiers/*`,
  `app/services/sync_candidate_service.py`.
- **Related flows**: `02-chunking-and-contextualization.md`,
  `03-embeddings-and-vector-store.md`,
  `04-lexical-and-fuzzy-index.md`,
  `13-observability-eval-versioning.md`.
- **Canonical design docs**: `docs/architecture.md` §7,
  `docs/rag-pipeline.md` §1.
