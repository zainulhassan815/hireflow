# RAG pipeline — current-state reference

Canonical description of how Hireflow ingests documents and serves
search / Q&A. Companion to `architecture.md` (system-wide) and
`rag-architecture.md` (design rationale).

Keep this doc in sync with the code. When a slice lands that changes
either pipeline, update the diagram + component map below.

---

## 1. Ingestion pipeline (worker)

Runs in a Celery worker — HTTP upload returns `201` with
`status=PENDING` immediately, processing happens out-of-band.

```
┌────────────────────┐     ┌──────────────────────┐     ┌───────────────────────────┐
│  POST /documents   │───▶ │  Postgres row        │───▶ │  Celery task              │
│  (HR or admin)     │     │  status=PENDING      │     │  extract_document_text()  │
└──────────┬─────────┘     │  owner_id=actor.id   │     └────────────┬──────────────┘
           │               │  storage_key=…       │                  │
           ▼               └──────────────────────┘                  │
┌────────────────────┐ ◀──────────────────────────────────────────── │
│  MinIO blob        │                                               │
└────────────────────┘                                               │
                                                                     ▼
                        ┌────────────────────────────────────────────────────────┐
                        │  1. Extract  (app/adapters/text_extractors.py)         │
                        │  ─────────────────────────────────────────────────     │
                        │  UnstructuredExtractor                                  │
                        │    strategy = "hi_res" | "fast"                         │
                        │    infer_table_structure = True                         │
                        │                                                         │
                        │  Output: ExtractionResult(                              │
                        │    text:         str,  (reading-order joined body)      │
                        │    page_count:   int | None,                            │
                        │    elements:     list[Element]  (Title, NarrativeText,  │
                        │                                  ListItem, Table, …)    │
                        │  )                                                      │
                        │                                                         │
                        │  ImageExtractor (Tesseract) still handles raw images.   │
                        └──────────────────────────┬─────────────────────────────┘
                                                   ▼
                        ┌────────────────────────────────────────────────────────┐
                        │  2. Persist elements (F82.d)                            │
                        │  ─────────────────────────────────────────────────     │
                        │  document_elements table (1 row per typed region)       │
                        │    uniq (document_id, order_index)                      │
                        │    CASCADE on doc delete                                │
                        │  documents.extraction_version = EXTRACTION_VERSION      │
                        └──────────────────────────┬─────────────────────────────┘
                                                   ▼
                        ┌────────────────────────────────────────────────────────┐
                        │  3. Classify  (app/services/classification_service.py) │
                        │  Rule-based classifier (regex/keyword) → LLM fallback  │
                        │  Sets document_type + metadata.skills / experience_yrs │
                        └──────────────────────────┬─────────────────────────────┘
                                                   ▼
                        ┌────────────────────────────────────────────────────────┐
                        │  4. Chunk  (app/services/chunking.py)                  │
                        │  ─────────────────────────────────────────────────     │
                        │  chunk_elements(elements) → list[Chunk]                 │
                        │                                                         │
                        │  Rules (F82.e):                                         │
                        │   • Title / Header  → new chunk + section_heading meta │
                        │   • Table           → own chunk (HTML preferred)        │
                        │   • ListItem        → kept intact with narrative run   │
                        │   • NarrativeText   → greedy pack ~1200 chars          │
                        │   • Tiny doc (≤1500 chars)  → single chunk             │
                        │   • Oversize para   → sentence splitter fallback        │
                        │                                                         │
                        │  Chunk metadata: chunk_kind, section_heading,           │
                        │    page_number, element_kinds                          │
                        │  documents.chunking_version = CHUNKING_VERSION          │
                        └──────────────────────────┬─────────────────────────────┘
                                                   ▼
                        ┌────────────────────────────────────────────────────────┐
                        │  4b. Contextualize  (F82.c)                            │
                        │  ─────────────────────────────────────────────────     │
                        │  ChunkContextualizer (model-agnostic, any LlmProvider)  │
                        │  Three modes:                                           │
                        │   • summary:  1 summary call + N per-chunk calls       │
                        │   • full_doc: N per-chunk calls with whole doc body    │
                        │   • auto:     pick per-doc on extracted_text length    │
                        │   Produces chunk.context (50-100 words) situating the  │
                        │   chunk within the document for retrieval.             │
                        │                                                         │
                        │   Backed today by Claude Haiku (LLM_PROVIDER=anthropic) │
                        │   Swaps to Ollama / any future LlmProvider via config  │
                        │   Per-chunk failures are non-fatal (context=None)      │
                        └────────┬────────────────────────────────┬──────────────┘
                                 ▼                                ▼
        ┌────────────────────────────────────┐   ┌────────────────────────────────┐
        │  5a. Embed  (app/adapters/         │   │  5b. Postgres FTS              │
        │            embeddings/)            │   │  (auto)                        │
        │  ─────────────────────────────     │   │  ─────────────────────────     │
        │  EmbeddingProvider protocol        │   │  documents.search_tsv          │
        │   SentenceTransformerEmbedder      │   │    is a GENERATED tsvector     │
        │     (default BAAI/bge-small-       │   │    with setweight():            │
        │      en-v1.5, swappable)           │   │      A = filename               │
        │                                    │   │      B = metadata.skills        │
        │  Per-process singleton; lazy-load  │   │      C = extracted_text         │
        │  model on first use.               │   │    with normalize_tech_tokens  │
        │                                    │   │    SQL function applied to     │
        │  Output: vectors                   │   │    both filename + body.       │
        └─────────────┬──────────────────────┘   │  GIN index documents_search_   │
                      ▼                          │    tsv_idx                      │
        ┌────────────────────────────────────┐   │                                │
        │  6. Chroma upsert                  │   │  No Python code needed —       │
        │  (app/adapters/chroma_store.py)    │   │  populated by the database on  │
        │  ─────────────────────────────     │   │  every INSERT/UPDATE of        │
        │  Collection:                       │   │  extracted_text, filename, or  │
        │    documents_<model_slug>          │   │  metadata.                     │
        │  per-chunk metadata:               │   └────────────────────────────────┘
        │    document_id                     │
        │    owner_id                        │
        │    chunk_index, total_chunks       │
        │    chunk_kind                      │
        │    section_heading                 │
        │    page_number                     │
        │    element_kinds                   │
        │    chunking_version                │
        │  documents.embedding_model_version │
        │    = embedder.model_name           │
        └────────────────────────────────────┘
                      │
                      ▼
        ┌────────────────────────────────────┐
        │  status = READY, commit            │
        │  on_ready hook fires               │
        │    (auto-create Candidate from     │
        │     resume if type=resume)         │
        └────────────────────────────────────┘
```

**Retry** — Celery task is `acks_late=True`, `max_retries=3`,
`default_retry_delay=30`. Indexing failure is non-fatal for the
doc's overall status (it reaches READY anyway; chunks just aren't in
Chroma).

**Re-extraction trigger** — `uv run python -m scripts.reextract_all`.
Resets all non-pending docs to PENDING and enqueues the extract task.
Use after:
- Changing `extraction_strategy`
- Bumping `EXTRACTION_VERSION` or `CHUNKING_VERSION`
- Recovering from a worker crash

**Re-index (no re-extract)** — `uv run python -m scripts.reindex_embeddings`.
Rebuilds Chroma vectors from the persisted `document_elements` without
re-running the slow extraction step. Use after swapping
`EMBEDDING_MODEL`.

---

## 2. Query pipeline (FastAPI)

Runs inline in the request handler. No background jobs.

```
┌────────────────┐
│  User query    │
│  + filters     │
│  + actor       │
└───────┬────────┘
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│  SearchService.search(actor, query, document_type, skills, … , limit) │
│                                                                        │
│  Access control (F86):                                                 │
│    admin → owner_id=None (no filter)                                   │
│    HR    → owner_id=actor.id                                           │
│  Empty-query short-circuit (F88.a)                                     │
└───────┬────────────────────────────────────────────────────────────────┘
        │
        ├──────────────┬────────────────┬────────────────────┐
        ▼              ▼                ▼                    ▼
  ┌─────────────┐ ┌─────────────┐ ┌────────────────┐ ┌──────────────┐
  │  Vector     │ │  Lexical    │ │  SQL metadata  │ │  Fuzzy       │
  │  (Chroma)   │ │  (Postgres  │ │  (filters-only │ │  (pg_trgm,   │
  │             │ │   FTS)      │ │   path)        │ │   fallback)  │
  │  Query raw  │ │  Normalize  │ │                │ │              │
  │  (embeddings│ │  query:     │ │  document_type │ │  Fires only  │
  │  handle     │ │   acronyms  │ │  skills        │ │  when FTS    │
  │  acronyms / │ │   (F88.b)   │ │  experience    │ │  returns 0   │
  │  synonyms   │ │   tech      │ │  dates         │ │  (F88.c)     │
  │  already)   │ │   tokens    │ │                │ │              │
  │             │ │   (F88.d)   │ │                │ │  Uses strict │
  │  Chroma     │ │             │ │  owner_id      │ │  word_sim    │
  │  `where`    │ │  websearch_ │ │  filter (F86)  │ │  over        │
  │  clause:    │ │   to_tsquery│ │                │ │  filename +  │
  │  owner_id   │ │   (F88.a)   │ │                │ │  body        │
  │  +document  │ │             │ │                │ │              │
  │  _type      │ │  owner_id + │ │                │ │              │
  │  (F86 +F88) │ │  document_  │ │                │ │              │
  │             │ │  type fil-  │ │                │ │              │
  │  Distance   │ │  ters       │ │                │ │              │
  │  threshold  │ │             │ │                │ │              │
  │  (F80)      │ │  ts_rank_cd │ │                │ │              │
  │             │ │  over       │ │                │ │              │
  │  Drop       │ │  search_tsv │ │                │ │              │
  │  orphan     │ │  (F85+F87)  │ │                │ │              │
  │  chunks     │ │             │ │                │ │              │
  │  (F86.c)    │ │             │ │                │ │              │
  └──────┬──────┘ └──────┬──────┘ └────────┬───────┘ └──────┬───────┘
         │               │                 │                │
         └───────────────┴─────────────────┴────────────────┘
                                 │
                                 ▼
                  ┌─────────────────────────────────────┐
                  │  Reciprocal Rank Fusion (k=60)      │
                  │  Equal-weight today.                │
                  │  F85.c planned: weighted (boost     │
                  │  FTS filename-A over vector drift). │
                  └────────────────┬────────────────────┘
                                   ▼
                  ┌─────────────────────────────────────┐
                  │  (F80.5 planned)                    │
                  │  Cross-encoder reranker on top-K    │
                  └────────────────┬────────────────────┘
                                   ▼
                  ┌─────────────────────────────────────┐
                  │  Hydrate Document rows              │
                  │  (get_many)                         │
                  │  Drop non-READY (F86.b)             │
                  │  Confidence band (high/medium/low)  │
                  │  Attach highlight match_spans       │
                  │  (F92.1)                            │
                  └────────────────┬────────────────────┘
                                   │
                   ┌───────────────┴────────────────┐
                   ▼                                ▼
       /search — SearchResponse               /rag/query — RAG pipeline
         results[] with                         Stuff top chunks into prompt →
         snippets + match_spans                 Anthropic Claude Sonnet →
                                                answer + citations
                                                (citations carry match_spans
                                                 so highlight renders there too)
```

**Access control** is applied during retrieval, not as a post-filter
— prevents leaking even chunk existence / metadata for docs the actor
can't see. Same rule as `DocumentService._ensure_access`.

---

## 3. Component map

| Concern | Module / adapter | Notes |
|---|---|---|
| Blob storage | `adapters/minio_storage.py::MinioBlobStorage` | Sync for worker, async for API |
| Text extraction | `adapters/text_extractors.py::UnstructuredExtractor` | hi_res (GPU) or fast (CPU) |
| Image OCR | `adapters/vision/tesseract.py::TesseractVisionProvider` | For raw image uploads |
| Classification | `adapters/classifiers/` (RuleBasedClassifier → LLM fallback) | Sets `document_type` + extracts skills |
| Chunking | `services/chunking.py::chunk_elements` | Element-aware, F82.e |
| Contextualization | `adapters/contextualizers/llm.py::LlmChunkContextualizer` | F82.c; model-agnostic via `LlmProvider`; default Claude Haiku |
| Embedding | `adapters/embeddings/sentence_transformer.py` (default) | Behind `EmbeddingProvider` protocol, swappable |
| Vector store | `adapters/chroma_store.py::ChromaVectorStore` | Per-model collection naming |
| Lexical index | `documents.search_tsv` (Postgres generated column) | Weighted filename A / skills B / body C; tech-token normalization on both sides |
| Fuzzy fallback | `repositories/document.py::fuzzy_search` | `pg_trgm` `strict_word_similarity` |
| Search orchestration | `services/search_service.py::SearchService` | RRF merge, access control |
| Highlight | `services/highlight.py::find_match_spans` | F92.1; offset-based spans, no HTML in API |
| RAG | `services/rag_service.py::RagService` + `LlmProvider` | Claude Sonnet today |

---

## 4. Data model

```
Postgres
├── users                       roles: admin | hr
├── documents                   owner_id (FK users),
│                               extracted_text (for FTS),
│                               search_tsv tsvector (GENERATED, GIN),
│                               metadata (jsonb — skills, experience_yrs, …),
│                               extraction_version,
│                               chunking_version,
│                               embedding_model_version
│       ↓ cascade
├── document_elements           one row per typed region
│                               (kind, text, page_number, order_index,
│                                metadata jsonb)
│                               UNIQUE (document_id, order_index)
│                               Cache layer so re-chunking doesn't re-extract.
├── candidates                  one per resume doc (auto-created on READY)
├── jobs, applications          HR workflow
├── activity_log                audit trail
└── gmail_* tables              gmail ingest state (F50/F51)

ChromaDB
└── documents_<embedding_model_slug>   one collection per model
      per chunk:
        id = <document_id>:<chunk_index>
        document: the chunk text
        embedding: vector
        metadata:  document_id, owner_id, chunk_index, chunk_kind,
                   section_heading, page_number, element_kinds,
                   chunking_version, plus flattened doc-level fields
                   (filename, mime_type, document_type, skills, …)
```

---

## 5. Versioning & re-index flows

Each document is stamped at index time with three version labels:

- `extraction_version` — bumped when the extractor or its output shape
  changes (currently `v2-unstructured`). See
  `services/extraction_service.py::EXTRACTION_VERSION`.
- `chunking_version` — bumped when chunking rules change (currently
  `v2-element-aware`). See `services/chunking.py::CHUNKING_VERSION`.
- `embedding_model_version` — the HF model name used at last embed
  (e.g. `BAAI/bge-small-en-v1.5`).

Operational flows:

| Scenario | Command | What runs |
|---|---|---|
| Embedder swap (same chunks) | `scripts/reindex_embeddings.py` | Re-embed each doc's persisted chunks with the new model |
| Chunking rule change | bump `CHUNKING_VERSION` → `scripts/reextract_all.py` | Re-run full pipeline; new elements → new chunks → new vectors |
| Extractor change | bump `EXTRACTION_VERSION` → `scripts/reextract_all.py` | Same as above — extraction output is the input to chunking |
| Worker crash recovery | `scripts/reextract_all.py` | Resets stuck PROCESSING docs and re-enqueues |

Targeted re-index (only docs whose `embedding_model_version` differs
from current) is doable today via repo query; not scripted yet.

---

## 6. Known gaps (tracked in `docs/features.md`)

- **F82.b** whole-document chunk emission (helps broad "find a
  persona" queries)
- **F82.f** multi-granularity chunks (sentence / paragraph / section
  with parent-child retrieval)
- **F80.5** cross-encoder reranker on the merged top-K
- **F85.b** HF leaderboard model exploration via `EMBEDDING_MODEL`
  swap
- **F85.c** weighted RRF (filename-A boost over semantic drift)
- **F85.d** per-model `search_max_distance` travelling with the
  embedder instead of a global setting
- **F85.e** task-instruction prefixes for instruct-tuned embedders
  (e5, instructor, nomic)

See `docs/search-hardening.md` for P0–P3 correctness + UX gaps,
several of which are now resolved and are listed in
`docs/features.md` under F86–F88.
