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

- [ ] **F42 · Resume ↔ job matching & ranking**
  SRS: FR13, FR14 · Depends on: F41, F30
  - Score candidates per job (embedding similarity + skill overlap + heuristics)
  - `GET /jobs/{id}/candidates` sorted by score
  - Shortlist / reject actions (FR14, FR15)

- [ ] **F43 · Excel export**
  SRS: FR16, UC-05 · Depends on: F42
  - `GET /jobs/{id}/candidates/export` → xlsx (openpyxl)
  - Frontend export buttons on candidates + search pages

---

## Phase 5 — Gmail Integration (FR17, FR18, UC-08, UC-09)

- [ ] **F50 · Gmail OAuth connect**
  SRS: FR17 · Depends on: F14
  - OAuth 2.0 initiation + callback endpoints
  - Store refresh token encrypted per user
  - Settings page: connect/disconnect Gmail

- [ ] **F51 · Resume sync worker**
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

- [ ] **F60 · Activity log / audit trail**
  SRS: FR19, UC-10, §Privacy and Security · Depends on: F14
  - `ActivityLog` table (actor, action, resource, at, ip)
  - Middleware captures auth + document + job + email events
  - `GET /logs` with filters; `logs.tsx` wired

- [ ] **F61 · Settings & profile**
  Depends on: F13
  - Profile edit, password change, Gmail connection status, LLM/embedding provider selection

- [ ] **F62 · Dashboard metrics**
  Depends on: F20, F40, F41
  - Real counts (documents, jobs, candidates, recent activity) replacing mocks

---

## Phase 7 — Hardening & Deploy

- [ ] **F70 · Error handling & API error shape**
  Depends on: F10
  - Consistent error envelope; frontend toast integration; Sentry hook (optional)

- [ ] **F71 · Tests**
  Depends on: F10+
  - pytest: auth, documents, search, ranking
  - Playwright: login → upload → search happy path

- [ ] **F72 · Dockerfile + production compose**
  Depends on: F00
  - Backend + frontend Dockerfiles; reverse proxy (Caddy/Nginx); HTTPS
  - Separate `docker-compose.prod.yml`

- [ ] **F73 · Encryption at rest for sensitive fields**
  SRS: §Privacy and Security · Depends on: F50
  - OAuth refresh tokens + any PII columns encrypted (app-level or pgcrypto)

---

## Out of scope for v1
- ERP integrations, video tutorials, print-friendly quick-start, mobile apps
- GPU-optimized local LLM deployment (provider abstraction covers it later)
