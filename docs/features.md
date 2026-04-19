# Hireflow Feature Tracker

Main implementation tracker. Features are ordered by dependency — each assumes the previous ones are in place. Pick the next unchecked item.

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done

---

## Current focus

**Retrieval track complete** — F80, F80.5, F82.c/d/e, F85.a/c/d/f, F86, F87, F88 all landed. Pipeline shape: hybrid retrieval (vector + FTS + SQL metadata + trigram fallback) → weighted RRF → cross-encoder rerank → hydration → highlights. See `docs/rag-pipeline.md` for the current diagram.

Eval on 7-doc fixture: **P@5 0.252 · R@5 1.000 · MRR 0.859**. Ceiling hit on fixture size; further retrieval wins need corpus growth (more docs with overlapping vocabulary).

**Next track: Q&A.** Three features, all user-facing:

- **F81 — RAG answer quality** (backend-driven visible changes: streaming, tighter answers, confidence, citations, graceful failure). Sub-slices F81.a–j laid out below.
- **F92 — Search & RAG UX** (frontend chat polish: streaming UX, inline citations, regenerate, feedback, follow-ups, keyboard shortcuts, error states). Sub-slices F92.2–11 laid out below.
- **F96 — Persistent conversations** (ChatGPT-style): DB-backed chat history, sidebar, URL-per-conversation, survives reload. Foundational — F81.f / F92.9 sit on top of it.

They compose. Good first slice: **F96.a–e** (DB + API + streaming endpoint + URL routing) unlocks F81.a and F92.2 naturally. Alternative first slice: F81.a + F92.2 (streaming) if you'd rather ship perceived-latency wins before persistence.

---

## Phase 0 — Foundation

- [x] **F00 · Environment & config hardening**
  SRS: infra · Depends on: —
  - Enforce `JWT_SECRET_KEY` (no default; fail-fast on startup)
  - Drive CORS origins from env (`ALLOWED_ORIGINS`)
  - Real `.env.example` for Postgres, Redis, Chroma, JWT, Gmail OAuth, LLM provider
  - `backend/app/core/config.py` split: settings validated at import

- [x] **F01 · Database layer (Postgres + SQLAlchemy + Alembic)**
  SRS: infra · Depends on: F00
  - Async SQLAlchemy 2.x engine + session dependency
  - Alembic initialized with autogenerate
  - Base `User` model (id, email, hashed_password, role, timestamps)
  - First migration committed

- [x] **F02 · Generated API client & frontend wiring**
  SRS: infra · Depends on: F00
  - `openapi-ts` generation script wired into frontend build
  - Shared `apiClient` with base URL from env, auth header injection
  - Remove mock data scaffolding pattern; replace with real fetchers page-by-page as endpoints land

---

## Phase 1 — Authentication (FR01–FR03, UC-01, UC-02)

- [x] **F10 · Backend auth: register + login + JWT**
  SRS: FR01, FR03 · Depends on: F01
  - `POST /auth/register`, `POST /auth/login` return access + refresh tokens
  - Bcrypt/argon2 password hashing
  - `get_current_user` dependency; protect all non-public routes
  - Rate limit login attempts (address UC-01 open issue: account lock)

- [x] **F11 · Token refresh + logout**
  SRS: FR01 · Depends on: F10
  - `POST /auth/refresh`, `POST /auth/logout` (refresh-token revocation list in Redis)

- [x] **F12 · Password reset flow**
  SRS: FR02, UC-02 · Depends on: F10
  - `POST /auth/forgot-password` issues one-time reset token (email delivery stubbable)
  - `POST /auth/reset-password` validates token + sets new password
  - Password policy shared between FE/BE

- [x] **F13 · Frontend auth integration**
  SRS: FR01–FR03 · Depends on: F10–F12, F02
  - Replace `auth-provider.tsx` mock with real API calls
  - Secure token storage (httpOnly cookie preferred; else memory + refresh)
  - Route guards; 401 → auto-refresh → logout on failure

- [x] **F14 · RBAC scaffolding**
  SRS: §Privacy and Security · Depends on: F10
  - Role enum (`hr`, `admin`); route-level role checks
  - Seed script for initial admin

- [x] **F15 · Layered refactor: domain / adapters / repositories / services**
  Not user-facing. Moves auth/session/reset code behind `Protocol`s, adds
  `domain/exceptions.py` + an error-handler, introduces `repositories/`,
  formalises `Authorizer`. Routes become minimal HTTP wrappers. All F10–F14
  HTTP contracts preserved and re-exercised.
  Depends on: F14

- [x] **F20 · Document model + storage (MinIO)**
  Depends on: F15
  - Add MinIO to `docker-compose.yml` + one-shot bucket init
  - `Document` table (id, owner, filename, mime, size, storage_key, status, metadata JSONB, timestamps)
  - `BlobStorage` Protocol; `MinioBlobStorage` adapter (portable to S3/GCS via endpoint swap)

---

## Phase 2 — Documents (FR04–FR06, UC-03)

- [x] **F21 · Upload endpoint + frontend uploader**
  SRS: FR04 · Depends on: F20, F13
  - `POST /documents` multipart, size/MIME validation (PDF, DOCX, images)
  - Drag-and-drop + batch upload on `documents.tsx` wired to real API
  - List/preview/download/delete endpoints

- [x] **F22 · Text extraction pipeline (Celery + OCR + PDF/DOCX)**
  SRS: FR05, FR06 · Depends on: F21
  - Background worker (Redis + RQ/Arq or FastAPI `BackgroundTasks` initially)
  - PyMuPDF for PDFs, python-docx for Word, Tesseract for images/scanned PDFs
  - Persist extracted text + status transitions (`pending → processing → ready/failed`)

- [x] **F23 · Classification + metadata extraction**
  SRS: FR20, UC-11 · Depends on: F22
  - Classifier (rule-based first, LLM fallback): resume / report / contract / letter
  - Extract resume metadata (skills, experience years, education) into JSONB
  - `GET /documents/{id}/metadata`

---

## Phase 3 — Search & RAG (FR07–FR10, UC-03, UC-04)

- [x] **F30 · Embeddings + ChromaDB ingestion**
  Depends on: F22
  - Chunk + embed extracted text (sentence-transformers or OpenAI embeddings, configurable)
  - Write to Chroma with `document_id` + metadata
  - Re-index on document update/delete

- [x] **F31 · Hybrid search endpoint (vector + metadata)**
  SRS: FR07, FR09 · Depends on: F30
  - `POST /search` — natural-language query → ranked chunks + parent docs
  - Return snippets with highlights

- [ ] **F32 · Filters (skills / role / date / type)**
  SRS: FR08, FR10, UC-04 · Depends on: F31, F23
  - Hybrid filter: SQL metadata filter + vector similarity
  - Frontend `search.tsx` + `documents.tsx` filter UI wired

- [x] **F33 · RAG chat (Q&A over documents)**
  SRS: §RAG System · Depends on: F31
  - `POST /rag/query` streams answer + citations
  - LLM provider abstraction (Anthropic / OpenAI / local)
  - Chat UI on dashboard / dedicated page

---

## Phase 2.5 — Frontend Integration Sprint

Wire existing frontend pages to the real backend API. All pages must follow
`docs/frontend-api-rules.md`: SDK types only, no mock data, no custom types.

- [x] **F25 · Documents page**
  Depends on: F21
  - Upload via `documentsUploadDocument`, list via `documentsListDocuments`
  - Download, delete, metadata view against real API
  - Loading/empty/error states

- [x] **F26 · Search page**
  Depends on: F31
  - Wire to `searchSearchDocuments` with filter controls
  - Display ranked results with highlights and metadata

- [x] **F27 · RAG chat page**
  Depends on: F33
  - Integrated as tab in search page with `ragQueryDocuments`
  - Show answer + source citations with model info

- [x] **F28 · Dashboard**
  Depends on: F25
  - Real counts (documents, recent uploads)
  - Replace all mock data with API calls

---

## Phase 4 — Jobs & Candidates (FR11–FR16, UC-06, UC-07, UC-12)

- [x] **F40 · Jobs CRUD**
  SRS: FR11, FR12 · Depends on: F14
  - `Job` model (title, description, required_skills[], experience_min, education, status)
  - `GET/POST/PATCH/DELETE /jobs`
  - Frontend `jobs` pages wired

- [x] **F41 · Candidate model + resume linking**
  Depends on: F23, F40
  - `Candidate` (derived from processed resumes: name, email, skills[], experience, source_document_id)
  - `Application` join table (candidate ↔ job, status: new/shortlisted/rejected, score)

- [x] **F42 · Resume ↔ job matching & ranking**
  SRS: FR13, FR14 · Depends on: F41, F30
  - Score candidates per job (embedding similarity + skill overlap + heuristics)
  - `GET /jobs/{id}/candidates` sorted by score
  - Shortlist / reject actions (FR14, FR15)

- [x] **F43 · CSV export**
  SRS: FR16, UC-05 · Depends on: F42
  - `GET /jobs/{id}/candidates/export` → CSV (stdlib, no deps)
  - Frontend export buttons on candidates + search pages

---

## Phase 5 — Gmail Integration (FR17, FR18, UC-08, UC-09)

- [x] **F50 · Gmail OAuth connect**
  SRS: FR17 · Depends on: F14
  - OAuth 2.0 initiation + callback endpoints
  - Store refresh token encrypted per user
  - Settings page: connect/disconnect Gmail

- [x] **F51 · Resume sync worker**
  SRS: FR18, UC-08, UC-09 · Depends on: F50, F22
  - Scheduled poll (or push via Pub/Sub later) fetches new emails with attachments
  - Dedup by message-id + attachment hash
  - Ingest attachments through the existing document pipeline

- [ ] **F52 · Follow-up email sending**
  SRS: §Resume Screening · Depends on: F50
  - Template-based follow-ups from candidate detail view
  - Send via Gmail API; log in activity trail

---

## Phase 6 — Observability & Admin (FR19, FR20, UC-10, UC-11)

- [x] **F60 · Activity log / audit trail**
  SRS: FR19, UC-10, §Privacy and Security · Depends on: F14
  - `ActivityLog` table (actor, action, resource, at, ip)
  - Middleware captures auth + document + job + email events
  - `GET /logs` with filters; `logs.tsx` wired

- [x] **F61 · Settings & profile**
  Depends on: F13
  - Profile edit, password change, Gmail connection status, LLM/embedding provider selection

- [x] **F62 · Dashboard metrics**
  Depends on: F20, F40, F41
  - Real counts (documents, jobs, candidates, recent activity) replacing mocks

- [ ] **F63 · Dev-mode logging config**
  Depends on: —
  - Today the project has no root logging handler, so `logger.info(...)` from `app.*` gets dropped in dev runs (SQLAlchemy shows up because it configures its own handler; our modules don't).
  - Add a `DEBUG`-guarded `logging.basicConfig(level=INFO)` in `app/main.py` so dev runs surface observability lines like F81.b/c's `rag context: ...` without a custom log config.
  - Keep prod behaviour unchanged (container runtimes configure logging externally).
  - Small, self-contained. Surfaced as a follow-up from F81.b/c manual-testing where the INFO log was only visible via `caplog` in tests.

---

## Phase 7 — Hardening & Deploy

- [x] **F70 · Error handling & API error shape**
  Depends on: F10
  - Consistent error envelope; frontend toast integration; Sentry hook (optional)

- [x] **F71 · Tests**
  Depends on: F10+
  - pytest: auth, documents, search, ranking
  - Playwright: login → upload → search happy path

- [x] **F72 · Dockerfile + production compose**
  Depends on: F00
  - Backend + frontend Dockerfiles; reverse proxy (Caddy/Nginx); HTTPS
  - Separate `docker-compose.prod.yml`

- [x] **F73 · Encryption at rest for sensitive fields**
  SRS: §Privacy and Security · Depends on: F50
  - OAuth refresh tokens + any PII columns encrypted (app-level or pgcrypto)

---

## Phase 8 — Intelligence Enhancement

Improve accuracy, relevance, and usefulness of core AI features.

- [x] **F80 · Search relevance tuning**
  - Minimum similarity threshold — discard vector hits above cosine distance threshold (default 0.6) instead of returning everything
  - SQL metadata path only contributes when structured filters are present (no more "recent documents for any query")
  - Drop max-score normalization lie; expose a confidence band (`high`/`medium`/`low`) instead
  - Dedup + cap highlights per document (max 3 per doc)
  - Eval harness: 15-20 curated queries against fixture docs, precision@5 + MRR baseline via `make eval`
  - Deferred to F80.5 (below): query expansion, RRF recency boost, faceted results

- [x] **F80.5 · Cross-encoder reranker** — `Reranker` protocol + `CrossEncoderReranker` (BAAI/bge-reranker-base, local sentence-transformers) + `NullReranker` + registry. Wired into `SearchService` with `reranker_top_k=20`. Default `reranker_provider=local` after F85.c weighted RRF lands — the candidate set is filename-biased before reranking, so the reranker reshuffles within an already-correct window. Eval: MRR held at 0.859 with the combined stack.
  - Rerank top-20 vector candidates with a local cross-encoder (e.g. `cross-encoder/ms-marco-MiniLM-L-6-v2`)
  - Toggle via `SEARCH_RERANKER_ENABLED` env var for A/B
  - Eval harness measures precision@5 before/after to justify the `sentence-transformers` dep weight

- [ ] **F81 · RAG answer quality** — all user-facing (changes how the answer looks, feels, or what it knows). Proposed sub-slices:
  - [x] **F81.a** Streaming answers via SSE — `LlmProvider.stream` protocol method (async-native, no thread bridge) + `AsyncAnthropic.messages.stream` / `httpx.AsyncClient.stream` for Ollama. `RagService._build_context` shared between `query` and new `stream_query`. `POST /rag/stream` emits typed `StreamEvent` discriminated union (citations → delta\* → done, or error) as SSE frames via `StreamingResponse` + 5-line `_sse_frame` helper (no `sse-starlette`). Frontend consumes via a ~100-line `fetch` + `ReadableStream` parser in `src/api/rag-stream.ts` (no new deps). Chat UI swapped to Claude-style full-viewport layout with pinned input and per-message streaming cursor.
  - [x] **F81.b** Distance filter in `RagService._build_context`: drops hits above `rag_context_max_distance` (None → embedder threshold, same shape as F85.d search). When every hit fails the cutoff, returns `None` → existing no-hits sentinel fires without an LLM call. Live: irrelevant queries (`quantum mechanics`) now short-circuit in ~20ms instead of paying ~1400ms for the LLM to reason its way to "Not in the provided documents". No retrieval-pipeline change (still vector-only); F81.k tracks RAG adopting the full SearchService path.
  - [x] **F81.c** Token-budget pass in `_build_context`: walks hits in retrieval order, accumulates via a 4-chars-per-token heuristic (`_estimate_tokens`, no `tiktoken`), stops when the next chunk would push over `rag_context_token_budget` (default 4000 tokens — headroom for Ollama 8k, trivial for Claude 200k). Oversized top chunk kept with WARN (preserves answer capability). Observability: one INFO line per query `rag context: N/M chunks kept, ~K tokens (cutoff=X, budget=Y)`. Live with budget=500: 10-chunk request truncated to 7.
  - [x] **F81.d** System prompt rewritten to rules: exact "Not in the provided documents." sentinel on no-answer, inline `[filename.pdf]` citations per claim, anti-preamble clause (no "Based on the documents…"), bullet/table format hints, 200-word cap. Verified live against Claude Haiku: relevant queries produce `[file.pdf]` citations inline; irrelevant queries surface the sentinel verbatim. Softness: Haiku sometimes still opens with "Based on the provided documents" — known instruction-following gap of small models, not an infra issue.
  - [x] **F81.e** `confidence: Literal["high","medium","low"] | None` on `RagResponse` + `StreamDone`. Single compute via `_compute_confidence(kept)` in `_build_context` from top-chunk distance against `rag_confidence_high_max_distance=0.20` / `..._medium_max_distance=0.30` (bge-small-calibrated operator knobs). `None` when no answer was grounded — sentinel path emits null so the frontend hides the badge rather than render a pretend "low". Frontend chat bubble renders a green/amber/grey `<Badge>` next to `model · ms` metadata, same visual language as the search page's result chip. Helper signature takes the full `kept` list so future multi-signal extensions (spread, count, reranker score) slot in without a caller rewrite. Live-verified: strong query → `medium`, irrelevant query → `null`, sync + streaming paths produce identical values.
  - [ ] **F81.f** Conversation memory: track the last N message pairs per session in Redis, inject into the prompt. **User sees:** follow-ups like "what about the other resume?" and "show me more like that" work naturally.
  - [x] **F81.g** Embedding-based intent classifier over 10 intents (count/comparison/ranking/yes_no/locate/summary/timeline/extract/skill_list/list + `general` fallback). Canonicals as data (`intent_canonicals.py`), embedded once via the shared `EmbeddingProvider`. Three-layer prompt stack in `rag_prompts.py` (identity + evidence rules + per-intent format rules) + few-shots for comparison/ranking. `PROMPT_VERSION` logged for A/B. Frontend renders markdown (`react-markdown` + `remark-gfm`); citation chips survive inside table cells/list items via an AST text-node walker. Eval harness (`make eval-intent`) with 63 labeled queries + CI gate at 80%; live accuracy **93.7%** (100% on every specific intent). Live: "compare React and Svelte" → real markdown table, "does X use TypeScript" → starts with "Yes." on its own line.
  - [x] **F81.h** `SourceCitation` grew `section_heading: str \| None` and `page_number: int \| None`, pulled from `VectorHit.metadata` (F82.e already stamped both on chunks). Frontend source cards now render `filename · section_heading · p.{page_number}` and carry stable anchor ids; clicking a marker scrolls the matching card into view with a brief primary-ring flash. Full in-app doc preview modal deferred as F81.h2 — the section-heading + snippet in the sources panel already gives "see the relevant section" feedback without a new route.
  - [x] **F81.i** Typed LLM-provider error taxonomy. New `LlmProviderError` + `LlmUnavailable` (→503) / `LlmRateLimited` (→429, carries `retry_after_seconds` in `details`) / `LlmTimeout` (→504). Adapters translate `anthropic.*` and `httpx.*` errors via one `_translate_*` helper shared between sync `complete()` and async `stream()` — symmetric error boundary. `RagService.stream_query` emits typed `ErrorEvent` with the domain code; sync `/rag/query` gets a proper 503/429/504 envelope via the existing F70 handler. `DomainError.details()` method added (default None, backwards-compatible). Empty retrieval was already handled by F81.b's sentinel path. Unknown SDK exceptions re-raise → last-resort `llm_error` with full server-side traceback. Live-verified with bogus `ANTHROPIC_API_KEY`: streaming yields `code="llm_unavailable"`, sync returns 503. No new deps.
  - [x] **F81.j** Inline `[filename.pdf]` markers (Claude already emits them via F81.d) now render as clickable shadcn-Tooltip chips in the assistant bubble. `parseSegments` walks the streamed content, matching brackets exactly against `SourceCitation.filename` (case-insensitive fallback); unknown brackets render as plain text so there are no false-positive chips. Streaming-safe — regex only matches complete `[...]`, so incomplete markers stay as plain text until the next delta closes them. Tooltip shows filename + section heading + 3-line snippet; click scrolls to the source card (pairs with F81.h).
  - [x] **F81.k** RAG retrieval adopts the full `SearchService` pipeline (FTS + RRF + reranker). Today `RagService` retrieves vector-only via `vector_store.query`, missing F87 multi-field weighted FTS, F88 acronym expansion + typo tolerance, and F80.5 cross-encoder reranker scores. Architectural change — needs owner-scope threading (SearchService takes `owner_id`; RAG today doesn't), composition-root edits, and a decision on whether to share retrieval ordering with the displayed search results. Follow-up surfaced from F81.b/c where "rank chunks by reranker score" was scope-fenced out. **User sees:** RAG answers using retrieval-quality parity with the search page (no "but I searched for that and it was there" mismatches).

- [~] **F82 · Chunking strategy improvements** — mixed-doc corpus, not just resumes
  - [ ] **F82.a** (skipped — went straight to F82.d layout-aware extraction instead)
  - [ ] **F82.b** Whole-document chunk: one extra vector per doc with `chunk_kind="document"` holding a concatenated extract (first paragraph + headings + skills list). Helps broad "find me a [persona]" queries that need doc-level signal rather than any single chunk.
  - [x] **F82.d** Layout-aware extraction via `unstructured.partition` (hi_res strategy, GPU-accelerated via local RTX 5050). Persists typed elements (`Title`, `NarrativeText`, `ListItem`, `Table`, …) to `document_elements` + version columns on `documents` (`extraction_version`, `chunking_version`, `embedding_model_version`).
  - [x] **F82.e** Element-aware chunker: headings attached as `section_heading` metadata (not emitted as standalone chunks after F82.c follow-up), tables→own chunk (markdown preferred), lists→intact, narrative→packed ~1200 chars. `CHUNKING_VERSION=v3`.
  - [x] **F82.c** Contextual retrieval (Anthropic): `ChunkContextualizer` protocol backed by any `LlmProvider`; three modes (summary / full_doc / auto). Chunker no longer emits heading-only chunks (CHUNKING_VERSION v3) — heading text lives on subsequent narratives as `section_heading` metadata, saving ~40% of LLM calls per doc. Live wins visible: `menu analyzer` now ranks Menu Analyzer Portfolio at #1 (was #2 under Restaurant Signup). Eval held at P@5 0.252 / R@5 1.000 / MRR 0.859 — fixture corpus too small to show Anthropic's published -35%.
  - [ ] **F82.f** (later) Multi-granularity chunks: sentence + paragraph + section levels with parent-child retrieval. Enables retrieve-small-return-big.
  - Re-index required on any chunk strategy change — `scripts/reindex_embeddings.py` handles it.

- [ ] **F83 · Candidate matching accuracy**
  - Skill normalization: "JS" = "JavaScript", "k8s" = "Kubernetes", "ML" = "Machine Learning"
  - Weighted skill matching: required skills matter more than preferred, exact match > partial
  - Experience range scoring refinement: penalize overqualified less than underqualified
  - Education level hierarchy: PhD > Master's > Bachelor's > Associate's > Diploma
  - Location matching: remote preference, city proximity
  - Match explanation: human-readable sentence explaining why a score is high/low

- [ ] **F84 · Document classification accuracy**
  - Training data: curated examples per document type for the rule-based classifier
  - Confidence calibration: rule-based confidence should reflect actual accuracy
  - Multi-label support: a document can be both "resume" and "letter" (cover letter + CV combo)
  - Classification audit: log classified vs actual type, track accuracy over time
  - User correction: let HR override the classified type, feed back into the system

- [~] **F85 · Embedding quality** (F85.b/e still open — gated on real-corpus scale)
  - [x] **F85.a** Model-agnostic `EmbeddingProvider` protocol + `SentenceTransformerEmbedder` POC with `BAAI/bge-small-en-v1.5`. ChromaVectorStore takes pre-computed vectors; per-model collection naming; `scripts/reindex_embeddings.py`. Eval: P@5 0.253→0.252 (tied), R@5 0.974→**1.000**, MRR 0.870→0.841.
  - [ ] **F85.b** Model exploration — the single biggest unexplored retrieval lever. bge-small-en-v1.5 is a reasonable default but MTEB shows meaningful lift is available on small/base models that still fit on CPU. Candidates to A/B in rough priority order:
    - `intfloat/e5-base-v2` / `intfloat/e5-small-v2` — task-instructed, unlocks F85.e prefixes
    - `BAAI/bge-base-en-v1.5` — same family, bigger; usually +2–4 P@5 on MTEB retrieval
    - `nomic-ai/nomic-embed-text-v1.5` — long-context (8k), matryoshka dims; good for resumes that blow past 512 tokens
    - `jinaai/jina-embeddings-v2-base-en` — 8k context, competitive on MTEB
    - `mixedbread-ai/mxbai-embed-large-v1` — top of MTEB small/base tier; slower but may be worth it
    - `thenlper/gte-base` / `gte-large` — Alibaba; strong asymmetric-query scores
    Reference: https://huggingface.co/spaces/mteb/leaderboard (filter by "Retrieval (en)"). Recipe per candidate: (1) flip `EMBEDDING_MODEL` in `.env`; (2) `uv run python -m scripts.reindex_embeddings`; (3) `make eval`; (4) compare P@5 / R@5 / MRR against baseline. F85.d means `search_max_distance` auto-travels via the embedder table — add a row to `_MODEL_DISTANCE_THRESHOLDS` before evaluating so hits aren't wrongly filtered. Expected dev-corpus ceiling: current corpus is tiny (8 docs), so wins here will be modest; model exploration matters more once the real corpus grows.
  - [x] **F85.c** Weighted RRF: `_rrf_merge` takes `w_vector` / `w_sql` / `w_lexical` multipliers. Defaults bias lexical up (2.0) so F87's filename-A / skills-B weighting carries through to the merged ranking. Unlocked F80.5 reranker default-on (composes cleanly; MRR holds at 0.859).
  - [x] **F85.d** Per-model distance threshold travels with the embedder. `EmbeddingProvider` protocol now exposes `recommended_distance_threshold`; `SentenceTransformerEmbedder` ships a curated `_MODEL_DISTANCE_THRESHOLDS` table (BGE 0.35, MiniLM/mpnet 0.60, E5 0.50, nomic 0.45, jina 0.40) with a 0.5 default + one-time warning for unknown models. `settings.search_max_distance` is now `float | None` — None means "ask the embedder," an explicit float still overrides (operator knob). `SearchService._resolve_distance_threshold` reads via `ChromaVectorStore.embedder` property. Unlocks model swaps without silent relevance regressions.
  - [ ] **F85.e** Document-type-specific embedding prefixes: "resume: ..." vs "job description: ..." for models that support task instructions (e5, instructor, nomic). **Depends on F85.b** — no point before we adopt an instruct model.
  - [x] Hybrid retrieval: Postgres FTS (`ts_rank_cd`) folded into RRF — eval P@5 0.175→0.238 (+36%), `edge` bucket 0.0→0.4
  - [x] **F85.f** Embedding versioning + startup integrity log. Per-chunk `embedding_model_version` stamped at index time ✅. `ChromaVectorStore._log_startup_integrity` logs `collection=<name> model=<name> chunks=<N>` on construction and warns when the Chroma collection's `embedding_model` metadata drifts from the configured embedder (pointing operators to `scripts/reindex_embeddings.py`). Non-fatal — wrapped in try/except so diagnostics can't crash boot.

- [x] **F86 · Search correctness (P0)** — see `docs/search-hardening.md` §3
  - [x] Per-user ownership scoping (admin bypass) wired into vector `where`, FTS, and SQL metadata paths
  - [x] Status filter on vector path: non-READY docs with stale chunks no longer surface
  - [x] **F86.c** Drop orphan vector hits (Chroma chunks for deleted Postgres docs) before RRF — was poisoning ranking by giving high vector scores to nonexistent docs and pushing real lexical hits out of top-K
  - Tenancy decision: per-user with admin bypass, matches `DocumentService._ensure_access`

- [x] **F87 · Multi-field weighted FTS (P1)** — see `docs/search-hardening.md` §4
  - [x] Replaced `extracted_text_tsv` with weighted `search_tsv`: filename (A, regexp-tokenized for `_-./` separators), `metadata.skills` (B), `extracted_text` (C)
  - [x] `document_type` deliberately not indexed — `enum::text` is non-IMMUTABLE in Postgres; structured filter handles those 5 values better
  - [x] No `SearchService` changes; `ts_rank_cd` does the weighting automatically
  - Eval lift on top of F86: **P@5 0.238→0.253, R@5 0.906→0.974, MRR 0.781→0.868 (+11%)**; new `filename` bucket MRR=1.0; live `menu analyzer` query now ranks Menu Analyzer Portfolio Doc.pdf at #1

- [x] **F88 · Query syntax & understanding (P1 + P2)** — see `docs/search-hardening.md` §3
  - [x] **F88.a** Switch `plainto_tsquery` → `websearch_to_tsquery` (phrase/OR/NOT), empty/whitespace short-circuit at service edge, query length cap (1024 chars) — same eval baseline (additive syntax)
  - [x] **F88.b** Canonical acronym expansion (one-directional: `k8s → kubernetes`, `ml → machine learning`, `js → javascript`, ~25 entries; ambiguous like `cv`/`tf` omitted). Applied to FTS only; vector handles equivalence semantically.
  - [x] **F88.c** Typo tolerance: `pg_trgm` `word_similarity` fallback over filename **and body** (`GREATEST` of both) when FTS returns 0; threshold 0.25. Body fallback was added after a real user-reported case (`pyhton` returned 0 because no filename had `python`).
  - [x] **F88.d** Special-token preservation (`C++`/`C#`/`F#`/`.NET`/`Node.js`/`Objective-C`): mirrored substitution at index time (Postgres `normalize_tech_tokens` SQL function) and query time (Python helper)
  - Known limitations: negation (`-term`) only constrains the FTS path; vector RRF can still surface negated docs. Highlight tokenizer (F92.1) doesn't see normalized tokens — non-issue today since query/snippet share the raw input, but worth flagging if highlighting ever consumes the normalized form.

- [ ] **F89 · Search polish (P2 + P3)** — see `docs/search-hardening.md` §3
  - Recency tie-breaking: stable `created_at desc` when RRF scores tie
  - Pagination: add `offset` to `SearchRequest`
  - Mixed-language fallback: try `simple` analyzer when `english` produces empty tsvector
  - Skill normalization (coordinate with F83): canonical form for `python`/`Python`/`py3`
  - ~~Experience parsing: prose → numeric range~~ (superseded by F89.a below)
  - **Query parser family** — parse NL into structured filters + semantic residue before retrieval. Closes the gap between `docs/rag-architecture.md`'s design (query parser emits `QueryIntent`) and the current engine (raw string → hybrid retrieval). Populates structured filters (built in F32, UI-only today) automatically from chat queries.
    - [x] **F89.a.1** Repository-layer filter hardening. Skills filter now uses JSONB array containment (`metadata['skills'] @> '["python"]'::jsonb`) instead of substring ILIKE — fixes false positives (`"python"` query no longer hits `pythonic`/`jython`/`python3`), GIN-indexable. `experience_years` cast guarded with `jsonb_typeof = 'number'` so malformed values filter out instead of 500. 11 new real-Postgres tests; 330 passing overall. Caught a SQLAlchemy JSONB cast pitfall during dev (`cast(f'["..."]', JSONB)` double-encodes into a JSON string — fixed by passing the Python list directly; documented in source).
    - [x] **F89.a** `QueryParser` Protocol + `HeuristicQueryParser` (regex + known vocabulary; zero LLM, sub-millisecond per call). Extracts years / seniority / skills / document types / date ranges with conservative precedence (explicit wins, longest-match skills via custom non-alphanumeric boundary check for `c++`/`.net`/`node.js`, skills-alone gated behind `has_strong_filter` so loose "what is Python used for" preserves pure-semantic behaviour). Wires into `SearchService.search` (merge with user-provided filters, explicit > implicit) and `SearchService.retrieve_chunks` (activates SQL intersection on strong filters; pure-semantic queries preserve the F81.k default). 54 unit tests; `make eval-parser` with 60+ labeled cases — **100% F1** across every field. Live-verified: structured queries hit SQL intersection, pure-semantic queries unchanged, filter-heavy queries that don't match the corpus now honestly return nothing instead of hallucinating.
    - [ ] **F89.b** Named-entity extraction — candidate names → `document_ids` scoping ("Alice's Kubernetes experience" retrieves only from Alice's docs). Needs name-to-doc resolution via `DocumentRepository`. Heuristic first (capitalized tokens matched against indexed candidate names), LLM tier opt-in.
    - [x] **F89.c** Similarity search — `POST /documents/{id}/similar`. New `DocumentSimilarityStore` Protocol + second Chroma collection (`documents_whole_<model>`) holding one mean-pooled vector per document. Reuses chunk embeddings (no second embed pass). `EmbeddingService` now owns both chunk + doc upserts and the delete path mirrors on `DocumentService.delete`. `SearchService.find_similar_documents` enforces owner scoping via Chroma `where` plus a belt-and-braces post-hydrate check, excludes the source from results before truncation, drops non-READY neighbours, and raises a distinct `DocumentNotIndexed` 404 when the source has no vector (→ re-index). 33 new tests (pool helper, service branches, endpoint auth + envelope). Live-verified against the dev corpus: CV.pdf (résumé) → neighbours ordered plausibly, similarity in a sensible band. Distance threshold deliberately deferred (noted as follow-up).
    - [x] **F89.c.1** Frontend: surfaced similar documents inside the existing document preview dialog. SDK regenerated (no hand-edits); new `SimilarDocuments` component wraps the generated POST as a `useQuery` via a thin `queryOptions` helper (cached by source-doc id, gated on `enabled && status === "ready"`). Renders up to 5 neighbours with filename + doctype + similarity %; shimmer loading state; error copy switches on backend `code` (`document_not_indexed` → "not in the similarity index yet", `service_unavailable` → generic). Click-to-swap uses `overrideDoc` state + `key={activeDoc.id}` on the scroll body so Radix Dialog stays mounted (no flicker) and scroll resets on swap. Keyboard-activatable rows. Neighbour resolution hits `listDocumentsOptions` cache first, falls back to `getDocument`. Lint + TS clean. Live-verified on the 9-doc dev corpus. Follow-ups tracked: invalidation on upload/delete, list-view row clicks, section collapse, `/documents/:id` page.
    - [ ] **F89.d** Synonym / role-family expansion beyond F88.b acronyms — `frontend` → `React`/`Vue`/`Angular`; conservative domain taxonomy with eval-gated precision guards.
    - [ ] **F89.e** (later, if needed) LLM tier fallback on low-confidence heuristic parses — same pattern as the F81.g classifier Protocol.

---

## Phase 9 — UI/UX Polish

Production-grade interface with attention to detail, accessibility, and delight.

- [~] **F90 · Design revamp + system baseline** — full visual-identity pass.
  Kills AI-slop defaults and establishes tokens that F91–F96 inherit.
  Driven by the `/impeccable:critique` findings in
  `docs/dev/F90-design-revamp/01-critique.md` (baseline heuristic score
  23/40). Executed as eight sequential `/impeccable:*` passes; each gets
  its own dev folder under `docs/dev/F90X-<slug>/` with the standard
  five-doc workflow.
  - [x] **F90.a** `/impeccable:shape` — design brief. Pin brand name,
    voice, audience, tonal direction. Kills "ScreenAI + Sparkles".
    Everything downstream depends on this.
  - [x] **F90.b** `/impeccable:typeset` — typography system. Display face
    for headlines, real weight contrast, intentional tracking/leading.
  - [x] **F90.c** `/impeccable:colorize` — semantic categorical palette
    via OKLCH hue rotation. Status / intent / confidence get hue
    differentiation; blue stays primary-action only.
  - [x] **F90.d** `/impeccable:layout` — break the identical 4-KPI-card
    hero on Dashboard + Documents. Page-specific primary metrics with
    visualization; demote the rest.
  - [x] **F90.e** `/impeccable:bolder` — commit to `--radius: 0` opinion
    across all surfaces or abandon it. No half-hedging with rounded
    avatars/icons alongside sharp cards.
  - [x] **F90.f** `/impeccable:harden` — destructive-action confirms,
    skeleton loaders replace spinners, retry affordances, real empty-
    state voice.
  - [x] **F90.g** `/impeccable:delight` — brand moments: login hero,
    empty states, first-use onboarding. Peak-end rule targets.
  - [ ] **F90.h** `/impeccable:polish` — final pass: pure-black backdrop
    → brand-tinted, kill bounce animation, align spacing drift, document
    the resulting tokens.

  Originally-scoped bullets fold into sub-features above:
  - spacing/typography/color consistency → F90.b + F90.c
  - dark mode verification → F90.c
  - responsive audit → F90.h
  - loading skeletons → F90.f
  - transition animations → F90.e + F90.g

- [ ] **F91 · Documents page polish**
  - Drag-and-drop upload zone on the main page (not just in dialog)
  - Upload progress with real percentage (streaming upload)
  - Document processing status: live polling or WebSocket for pending → ready transition
  - Inline preview for PDFs (embedded viewer)
  - Bulk actions: select multiple → delete, export, create candidates

- [~] **F92 · Search & RAG UX** — frontend polish. Backend answer-quality lives in F81.
  - Search page:
    - Search-as-you-type with debounce
    - Filter pills: visual chips for active filters, one-click remove
    - [x] **F92.1** Search result highlighting: offset-based `match_spans` on `/search` and `/rag/query`; frontend `<HighlightedText>` renders `<mark>`
    - Suggested queries: show example queries when the search box is empty
    - Recent queries dropdown under the search input
    - Empty-state with illustrations + "try these" prompts
  - RAG chat:
    - [ ] **F92.2** Streaming chat UX: typing indicator, cursor animation while tokens arrive, stop-generation button, auto-scroll lock when the user is reading. Pairs with F81.a backend.
    - [ ] **F92.3** Inline clickable citation markers in the answer (pairs with F81.j). Hover tooltip shows source filename + context; click opens the source (pairs with F81.h).
    - [ ] **F92.4** Copy answer button (markdown) and copy-as-plaintext. Per-message copy + full-conversation export (markdown file).
    - [ ] **F92.5** Regenerate button on each assistant message — retry with same query, optionally with "give me a shorter answer" / "be more technical" variants.
    - [ ] **F92.6** Thumbs-up / thumbs-down on each answer, persisted to a feedback table. Optional free-text reason on thumbs-down. Drives future prompt-tuning.
    - [ ] **F92.7** Suggested follow-up questions beneath each assistant message — generated by the LLM in the same turn as the answer (cheap piggyback call). Drives discovery.
    - [ ] **F92.8** Doc-scope selector: "Ask about: [all documents / this one / selected…]". Limits retrieval to chosen IDs via the existing `document_ids` param on `/rag/query`.
    - [ ] **F92.9** Conversation management: new-chat button, sidebar list of past conversations, rename, delete, search across conversations. Backs F81.f conversation memory.
    - [ ] **F92.10** Keyboard shortcuts: ⌘+Enter to send (already works), ⌘+N new chat, ⌘+K focus search, Escape to stop generation, ↑ to edit last message.
    - [ ] **F92.11** Error / empty-state UX: network down, LLM rate-limited, no retrieval hits — clear messaging + "retry" affordance. Pairs with F81.i backend.

- [ ] **F93 · Jobs & candidates UX**
  - Job detail page with description, requirements, and matched candidates list
  - Candidate profile page: resume viewer + extracted info + application history
  - Kanban board view for applications (drag between new/shortlisted/rejected/hired)
  - Match score visualization: radar chart or bar breakdown (skills/experience/vector)
  - One-click "create candidates from all resumes" batch action
  - CSV export button directly on the candidates table

- [ ] **F94 · Dashboard & navigation**
  - Activity feed: recent actions as a timeline (not just table)
  - Quick actions: upload, create job, search from dashboard
  - Keyboard shortcuts: ⌘K for search, ⌘U for upload
  - Breadcrumbs on nested pages (job detail, candidate profile)
  - Empty states with illustrations, not just icons
  - Toast notifications: success/error/info with consistent styling

- [ ] **F95 · Accessibility & performance**
  - ARIA labels on all interactive elements
  - Keyboard navigation: tab order, focus rings, escape to close modals
  - Screen reader testing on core flows (login, upload, search)
  - Lighthouse audit: target 90+ on performance, accessibility, best practices
  - Bundle analysis: lazy-load heavy pages (search, RAG chat)
  - Image optimization: proper formats, lazy loading

- [ ] **F96 · Persistent conversations (ChatGPT-style)** — replaces today's
  in-memory chat state in `SearchPage` with proper multi-conversation chat:
  sidebar, history, URL-per-conversation, survives page reload. Compose
  with F81.f (prompt-injected memory) and F92.9 (UI sidebar) — F96 is the
  persistence layer both sit on.

  Backend:
  - [ ] **F96.a** Schema: `conversations` (id, owner_id, title, created_at,
    updated_at, archived, metadata jsonb) + `chat_messages` (id,
    conversation_id, role, content, citations jsonb, model, tokens,
    created_at). Alembic migration + cascade on owner delete.
  - [ ] **F96.b** REST API: `POST/GET/PATCH/DELETE /conversations`,
    `POST /conversations/{id}/messages` (replaces direct `/rag/query`),
    `GET /conversations/{id}/messages`. Owner-scoped per F86.
  - [ ] **F96.c** Auto-title: after the first exchange, cheap Haiku call
    summarizes the question into a 3-6 word title. Stored on the
    conversation row; user-editable.
  - [ ] **F96.d** Streaming on `POST /conversations/{id}/messages` via SSE —
    composes with F81.a. Persist the completed assistant message only on
    stream close; show-but-don't-save during generation.

  Frontend:
  - [ ] **F96.e** Route per conversation: `/chat/:id`. New-chat creates
    lazily on first message. Direct URL load hydrates from API.
  - [ ] **F96.f** Sidebar (replaces the placeholder in F92.9): list
    conversations grouped by recency (Today / Yesterday / Past week /
    Older), rename-inline, archive/delete, search across titles + message
    content.
  - [ ] **F96.g** Migration path: the current `SearchPage` chat state moves
    into a dedicated `ChatPage`; the Search tab stays as search-only; the
    Q&A tab links into the new chat route on first message.

  Decisions worth pinning before starting:
  - Shared vs private conversations — default private per-user; shareable
    links as a later F96.h if needed.
  - Delete = soft (`archived=true`) or hard (remove row + cascade
    messages)? Default soft for recoverability.
  - Retention policy — auto-archive conversations with no activity in N
    days? Default: no auto-archive until we have data to tune on.

---

## Out of scope for v1
- ERP integrations, video tutorials, print-friendly quick-start, mobile apps
- GPU-optimized local LLM deployment (provider abstraction covers it later)
- Gmail integration (Phase 5 — deferred, needs Google OAuth setup)
