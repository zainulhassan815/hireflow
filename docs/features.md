# Hireflow Feature Tracker

Main implementation tracker. Features are ordered by dependency — each assumes the previous ones are in place. Pick the next unchecked item.

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done

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

- [ ] **F80.5 · Cross-encoder reranker**
  - Rerank top-20 vector candidates with a local cross-encoder (e.g. `cross-encoder/ms-marco-MiniLM-L-6-v2`)
  - Toggle via `SEARCH_RERANKER_ENABLED` env var for A/B
  - Eval harness measures precision@5 before/after to justify the `sentence-transformers` dep weight

- [ ] **F81 · RAG answer quality**
  - Structured answer templates: count queries → return number + list, comparison queries → table format, skill queries → bullet points
  - Context relevance filtering — drop chunks that are below similarity threshold before sending to LLM (reduces noise)
  - System prompt tuning: be concise, format matters, answer the specific question asked
  - Token budget management: prioritize high-relevance chunks, truncate low-relevance ones
  - Answer confidence indicator: if context is thin, say so explicitly and suggest uploading more documents
  - Support follow-up context (conversation memory within a session)

- [ ] **F82 · Chunking strategy improvements**
  - Semantic chunking: split on topic boundaries, not character count
  - Overlap tuning per document type (resumes need different chunking than reports)
  - Metadata-enriched chunks: each chunk carries its section header (Skills, Experience, Education) for better retrieval
  - Re-index existing documents when chunking strategy changes

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

- [~] **F85 · Embedding quality**
  - Evaluate embedding model options: all-MiniLM-L6-v2 vs all-mpnet-base-v2 vs instructor-xl
  - Document-type-specific embedding prefixes: "resume: ..." vs "job description: ..."
  - [x] Hybrid retrieval: Postgres FTS (`ts_rank_cd`) folded into RRF — eval P@5 0.175→0.238 (+36%), `edge` bucket 0.0→0.4
  - Embedding versioning: track which model generated each chunk's embedding, re-index on model change

- [ ] **F86 · Search correctness (P0)** — see `docs/search-hardening.md` §3
  - **Bug**: `routes/search.py:25-43` accepts `current_user` but never forwards it; every user sees every doc
  - Forward `owner_id` into vector `where` filter, FTS predicate, and SQL metadata path
  - Tenancy decision: per-user scoping vs shared HR pool (admin bypasses either way) — flag in plan
  - Filter `status = READY` in the vector path (FTS already does)
  - Eval: add cases verifying other-user docs and non-READY docs are excluded

- [ ] **F87 · Multi-field weighted FTS (P1)** — see `docs/search-hardening.md` §4
  - Replace `extracted_text_tsv` with weighted `search_tsv` generated column:
    - Weight A (highest): `filename`
    - Weight B: `document_type`, `metadata.skills`, `metadata.summary`
    - Weight C (lowest): `extracted_text`
  - `ts_rank_cd` automatically respects A>B>C; no `SearchService` changes
  - Single Alembic migration replacing the F85 column + GIN index
  - Eval: add filename-only and metadata-only query cases; expect P@5 lift

- [ ] **F88 · Query syntax & understanding (P1 + P2)** — see `docs/search-hardening.md` §3
  - Switch `plainto_tsquery` → `websearch_to_tsquery` (phrase/OR/NOT support)
  - Empty / whitespace / stopword-only query short-circuit
  - Query length cap (~256 tokens) to bound tsquery cost
  - Acronym / synonym map at query time (~30 HR-domain entries to start: JS↔JavaScript, K8s↔Kubernetes, ML↔machine learning, …)
  - Typo tolerance: `pg_trgm` similarity fallback when `ts_rank_cd` returns empty
  - Special-token preservation (`C++`, `.NET`, `Node.js`, `C#`) on both index and query side; share helper with F92.1 highlight tokenizer

- [ ] **F89 · Search polish (P2 + P3)** — see `docs/search-hardening.md` §3
  - Recency tie-breaking: stable `created_at desc` when RRF scores tie
  - Pagination: add `offset` to `SearchRequest`
  - Mixed-language fallback: try `simple` analyzer when `english` produces empty tsvector
  - Skill normalization (coordinate with F83): canonical form for `python`/`Python`/`py3`
  - Experience parsing: prose → numeric range (`5+ years`, `senior`)

---

## Phase 9 — UI/UX Polish

Production-grade interface with attention to detail, accessibility, and delight.

- [ ] **F90 · Design system audit**
  - Consistent spacing, typography scale, color usage across all pages
  - Dark mode: verify every component, fix contrast issues
  - Responsive: test and fix all pages at mobile, tablet, desktop breakpoints
  - Loading skeletons on every page (replace spinners with content-shaped placeholders)
  - Transition animations: page transitions, list item enter/exit, modal open/close

- [ ] **F91 · Documents page polish**
  - Drag-and-drop upload zone on the main page (not just in dialog)
  - Upload progress with real percentage (streaming upload)
  - Document processing status: live polling or WebSocket for pending → ready transition
  - Inline preview for PDFs (embedded viewer)
  - Bulk actions: select multiple → delete, export, create candidates

- [~] **F92 · Search & RAG UX**
  - Search-as-you-type with debounce
  - Filter pills: visual chips for active filters, one-click remove
  - [x] **F92.1** Search result highlighting: offset-based `match_spans` on `/search` and `/rag/query`; frontend `<HighlightedText>` renders `<mark>`
  - RAG chat: streaming responses (SSE), typing indicator, copy answer button
  - Source citation links: click citation → opens document preview at relevant section
  - Suggested queries: show example queries when search is empty

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

---

## Out of scope for v1
- ERP integrations, video tutorials, print-friendly quick-start, mobile apps
- GPU-optimized local LLM deployment (provider abstraction covers it later)
- Gmail integration (Phase 5 — deferred, needs Google OAuth setup)
