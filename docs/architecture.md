# System Architecture

Reference for how Hireflow is structured. Read this before touching code.

---

## 1. Infrastructure topology

### Development

```
Host machine
  ├── :5173  Vite dev server (frontend)
  ├── :8080  uvicorn (backend API)
  ├── Celery worker (background tasks)
  │
  └── Docker services (ports exposed to host for dev):
        ├── :5432  PostgreSQL 15
        ├── :6379  Redis 7
        ├── :9000  MinIO S3 API
        ├── :9001  MinIO console
        └── :8000  ChromaDB
```

### Production (`docker-compose.prod.yml`)

```
Internet
  │
  :80 ──→ nginx (frontend static + /api/ reverse proxy)
              │
              ├──→ backend:8080  (uvicorn)
              ├──→ worker         (celery, same Docker image)
              │
              └── internal network (no host ports) ──┐
                    postgres:5432 (password required) │
                    redis:6379 (password required)    │
                    minio:9000                        │
                    chromadb:8000                     │
                    ──────────────────────────────────┘
```

Only nginx port 80 is exposed. All data stores are on a private Docker
network. Redis and Postgres require passwords via env vars with `:?`
fail-fast guards.

---

## 2. Layered architecture

```
app/
├── domain/          ← pure business rules, no infra imports
├── models/          ← SQLAlchemy ORM (7 models)
├── schemas/         ← Pydantic request/response DTOs
├── repositories/    ← data access (one class per aggregate)
├── adapters/        ← Protocol definitions + concrete implementations
│   ├── vision/      ← pluggable OCR (Claude, Ollama, Tesseract)
│   ├── classifiers/ ← document classification (rule-based + LLM)
│   └── llm/         ← text LLM providers (Claude, Ollama)
├── services/        ← application orchestration (10 services)
├── api/             ← HTTP layer (routes, deps, error handlers)
├── worker/          ← Celery tasks
└── core/            ← cross-cutting (config, db, redis)
```

### Layer rules

| Layer | May import | Must NOT import |
|-------|-----------|-----------------|
| `domain/` | stdlib only | anything infra |
| `models/` | stdlib, sqlalchemy, `domain/` | services, routes, adapters |
| `schemas/` | stdlib, pydantic, `models/` (enums only) | services, routes |
| `repositories/` | `models/`, `domain/`, sqlalchemy | services, routes, adapters |
| `adapters/` | `core/`, stdlib, 3rd-party clients, `adapters/protocols` | services, repos, routes |
| `services/` | `repositories/`, `adapters/` (Protocols only), `domain/` | routes, FastAPI, HTTPException |
| `api/routes/` | `services/`, `schemas/`, `api/deps` | sqlalchemy, adapters (concrete), repos |
| `worker/tasks` | `services/`, `adapters/`, `core/` | routes, FastAPI |

**Key invariant:** services raise `DomainError` subclasses, never
`HTTPException`. The error handler in `api/error_handlers.py` maps
them to HTTP status codes.

---

## 3. Domain layer

### Exceptions (`domain/exceptions.py`)

| Exception | HTTP | When |
|-----------|------|------|
| `InvalidCredentials` | 401 | Wrong email/password |
| `InvalidToken` | 401 | Expired/revoked/malformed token |
| `AccountDisabled` | 403 | User deactivated |
| `Forbidden` | 403 | Role/ownership check failed |
| `NotFound` | 404 | Resource doesn't exist |
| `EmailAlreadyRegistered` | 409 | Duplicate registration |
| `FileTooLarge` | 413 | Upload exceeds `MAX_FILE_SIZE_MB` |
| `UnsupportedFileType` | 415 | MIME type not allowed |

### Authorizer (`domain/authorization.py`)

Business-level permission checks called from services. HTTP-layer
`require_role()` in `api/deps.py` provides defense-in-depth.

---

## 4. Adapter layer

### Protocols (`adapters/protocols.py`)

| Protocol | Implementations | Purpose |
|----------|----------------|---------|
| `PasswordHasher` | `Argon2Hasher` | Hash/verify passwords |
| `TokenIssuer` | `JwtTokenIssuer` | Issue/decode JWT tokens |
| `RevocationStore` | `RedisRevocationStore` | Denylist refresh JTIs |
| `ResetTokenStore` | `RedisResetTokenStore` | One-time password-reset tokens |
| `EmailSender` | `LoggingEmailSender` | Email delivery (stub → SES/SMTP) |
| `BlobStorage` | `MinioBlobStorage` | Object storage (MinIO → S3/GCS) |
| `VisionProvider` | Claude, Ollama, Tesseract | OCR for scanned documents |
| `DocumentClassifier` | RuleBased, Llm, Composite | Document classification |
| `TextExtractor` | Pdf, Docx, Image, Composite | Text extraction from files |
| `VectorStore` | `ChromaVectorStore` | Vector embeddings for search |
| `LlmProvider` | Claude, Ollama | Text completion for RAG |

### Shared data objects (frozen dataclasses)

`TokenPayload`, `StoredBlob`, `ExtractionResult`, `ClassificationResult`,
`VectorHit`

### Vision provider system (`adapters/vision/`)

Runtime-selectable via `VISION_PROVIDER`: `claude`, `ollama`, `tesseract`, `none`.
Resolved at Celery task execution time for runtime switching.

### LLM provider system (`adapters/llm/`)

Runtime-selectable via `LLM_PROVIDER` + `LLM_MODEL`. Used for RAG
question-answering and LLM-based document classification fallback.

### Classifier system (`adapters/classifiers/`)

Two-stage: rule-based first (keyword density + regex), LLM fallback
when confidence < 0.4. `CompositeClassifier` chains them.

---

## 5. Data model

```
users
├── id              UUID PK
├── email           VARCHAR(320) UNIQUE INDEX
├── hashed_password VARCHAR(255)
├── full_name       VARCHAR(255) NULLABLE
├── role            ENUM(hr, admin)
├── is_active       BOOLEAN
├── created_at      TIMESTAMPTZ DEFAULT now()
└── updated_at      TIMESTAMPTZ DEFAULT now()

documents
├── id              UUID PK
├── owner_id        UUID FK→users ON DELETE CASCADE INDEX
├── filename        VARCHAR(512)
├── mime_type       VARCHAR(128)
├── size_bytes      BIGINT
├── storage_key     VARCHAR(1024) UNIQUE
├── status          ENUM(pending, processing, ready, failed) INDEX
├── document_type   ENUM(resume, report, contract, letter, other) NULLABLE
├── extracted_text  TEXT NULLABLE
├── metadata        JSONB NULLABLE
├── created_at/updated_at TIMESTAMPTZ

jobs
├── id              UUID PK
├── owner_id        UUID FK→users ON DELETE CASCADE INDEX
├── title           VARCHAR(255)
├── description     TEXT
├── required_skills VARCHAR[] (PG ARRAY)
├── preferred_skills VARCHAR[] NULLABLE
├── education_level VARCHAR(100) NULLABLE
├── experience_min  INTEGER
├── experience_max  INTEGER NULLABLE
├── location        VARCHAR(255) NULLABLE
├── status          ENUM(draft, open, closed, archived) INDEX
├── created_at/updated_at TIMESTAMPTZ

candidates
├── id                  UUID PK
├── owner_id            UUID FK→users ON DELETE CASCADE INDEX
├── source_document_id  UUID FK→documents ON DELETE SET NULL UNIQUE INDEX
├── name                VARCHAR(255) NULLABLE
├── email               VARCHAR(320) NULLABLE
├── phone               VARCHAR(50) NULLABLE
├── skills              VARCHAR[] (PG ARRAY)
├── experience_years    INTEGER NULLABLE
├── education           VARCHAR[] NULLABLE
├── created_at/updated_at TIMESTAMPTZ

applications
├── id              UUID PK
├── candidate_id    UUID FK→candidates ON DELETE CASCADE INDEX
├── job_id          UUID FK→jobs ON DELETE CASCADE INDEX
├── status          ENUM(new, shortlisted, rejected, interviewed, hired) INDEX
├── score           FLOAT NULLABLE
├── created_at/updated_at TIMESTAMPTZ

activity_logs
├── id              UUID PK
├── actor_id        UUID FK→users ON DELETE SET NULL INDEX
├── action          ENUM(14 action types) INDEX
├── resource_type   VARCHAR(50) NULLABLE
├── resource_id     VARCHAR(255) NULLABLE
├── detail          TEXT NULLABLE
├── ip_address      VARCHAR(45) NULLABLE
├── created_at/updated_at TIMESTAMPTZ
```

All models inherit `UUIDPrimaryKeyMixin` + `TimestampMixin`.
Migrations: Alembic async. Downgrade scripts explicitly `DROP TYPE`
for PG enums.

---

## 6. Authentication system

```
Register → Login → Access Token (30m) + Refresh Token (7d)
                        │                      │
                    use on /api/*           POST /auth/refresh
                        │                      │
                   401 on expiry         revoke old, issue new pair
                        │                      │
                 auto-refresh (FE)        rotation prevents reuse
```

- **Argon2id** hashing with transparent rehash on login
- **Timing-safe** auth (dummy hash for missing users)
- **Type claim** on JWT prevents cross-use of access/refresh tokens
- **Redis denylist** for revoked JTIs (auto-expire with TTL)
- **Password reset**: opaque token, SHA-256 hashed in Redis, 15min TTL, atomic GET+DEL

---

## 7. Document processing & search — pipelines

Detailed diagrams, component map, and re-index flows live in
`docs/rag-pipeline.md`. Quick summary:

**Ingestion** (Celery worker, triggered on upload):
1. Fetch blob from MinIO
2. `UnstructuredExtractor` (hi_res on GPU or fast on CPU) produces
   typed `Element`s (`Title`, `NarrativeText`, `ListItem`, `Table`, …);
   persisted to `document_elements`
3. Classify (rule-based → LLM fallback); sets `document_type` +
   `metadata.skills`
4. `chunk_elements()` — heading/table/list/narrative-aware chunking
   with section-heading + page metadata
5. Embed via `EmbeddingProvider` (default `bge-small-en-v1.5`, swappable)
6. Upsert to Chroma (per-model collection) + Postgres `search_tsv`
   auto-populated
7. `status=READY`; on_ready hook fires (auto-candidate for resumes)

Version-stamped at each step (`extraction_version`,
`chunking_version`, `embedding_model_version`) to support targeted
re-index. Celery: `acks_late=True`, 3 retries, 30s delay. Indexing
failure is non-fatal.

Re-extraction: `scripts/reextract_all.py`. Re-index (vectors only):
`scripts/reindex_embeddings.py`.

---

## 8. Search & RAG — retrieval

Four signals merged via Reciprocal Rank Fusion (k=60) in
`SearchService.search`:

1. **Vector** — Chroma cosine on chunk embeddings; filtered by
   `owner_id` + `document_type` + distance threshold; orphan chunks
   dropped.
2. **Lexical FTS** — `ts_rank_cd` over `search_tsv` (weighted
   filename-A / skills-B / body-C); uses `websearch_to_tsquery` with
   acronym expansion and tech-token normalization on both sides.
3. **SQL metadata** — only engaged when structured filters are
   provided (`document_type`, `skills`, `experience_years`, dates).
4. **Fuzzy** — `pg_trgm` `strict_word_similarity` fallback when FTS
   returns zero (typo tolerance).

All paths respect `owner_id` (per-user scoping, admin bypass) and
`status=READY`.

`/search` returns ranked docs with snippets + highlight `match_spans`.
`/rag/query` stuffs top chunks into a Claude Sonnet prompt and
returns `answer + citations`. Full diagrams and component map:
`docs/rag-pipeline.md`.

### Candidate matching (`POST /jobs/{id}/match`)

Three-signal scoring per candidate:
- **Skill overlap (45%)**: jaccard on required + preferred skills
- **Experience fit (20%)**: 1.0 if in range, linear decay outside
- **Vector similarity (35%)**: ChromaDB cosine vs job description

Creates/updates `Application` records with computed scores.

---

## 9. Composition root (`api/deps.py`)

Wires adapters → services. Every route uses `Annotated` dep aliases.

```python
# Singletons
_hasher, _token_issuer, _email_sender, _blob_storage, _vector_store, _llm_provider

# Service factories (called per-request)
get_auth_service, get_session_service, get_password_reset_service,
get_document_service, get_search_service, get_rag_service,
get_job_service, get_candidate_service, get_matching_service,
get_user_service, get_activity_service

# Dep aliases
AuthServiceDep, SessionServiceDep, DocumentServiceDep, SearchServiceDep,
RagServiceDep, JobServiceDep, CandidateServiceDep, MatchingServiceDep,
ActivityServiceDep, UserServiceDep, CurrentUser, RequireAdmin
```

---

## 10. API surface

All routes under `/api`.

| Tag | Endpoints | Key operations |
|-----|-----------|----------------|
| auth | 9 | register, login, refresh, logout, forgot/reset password, me, update profile, change password |
| documents | 6 | upload, list, get, metadata, download, delete |
| search | 1 | hybrid search with filters |
| rag | 1 | question-answering with citations |
| jobs | 6 | CRUD + match candidates + CSV export |
| candidates | 6 | create from doc, list, get, apply to job, list apps, update status |
| users | 1 | list all (admin) |
| logs | 1 | activity audit trail with filters |

**Total: 31 endpoints.**

---

## 11. Frontend architecture

### Stack
React 19, TypeScript, Vite, Tailwind v4, shadcn/ui, TanStack Query

### SDK generation
```
backend OpenAPI spec → hey-api/openapi-ts → TypeScript SDK + React Query hooks
```

Operation IDs use route function names only (no tag prefix):
`listDocuments`, `uploadDocument`, `searchDocuments`, `queryDocuments`

### Data fetching pattern
```tsx
// Queries (GET endpoints) — auto-generated queryOptions
const { data, isLoading } = useQuery({
  ...listDocumentsOptions(),
  select: (data) => data ?? [],
});

// Mutations (POST/PATCH/DELETE) — with cache invalidation
const deleteMut = useMutation({
  mutationFn: (doc) => deleteDocument({ path: { document_id: doc.id } }),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: listDocumentsOptions().queryKey }),
});
```

### Auth flow
- `AuthProvider` calls `readMe()` on mount to hydrate user
- `src/api/client.ts` has request interceptor (Bearer token) + response interceptor (401 → single-flight refresh → replay)
- `PublicOnlyRoute` redirects authenticated users away from auth pages

### Pages wired to real API
Dashboard, Documents (CRUD + upload + preview), Search (hybrid + RAG chat),
Jobs (CRUD), Candidates (list), Logs (activity trail), Settings (profile + password)

---

## 12. Configuration

All settings via `pydantic-settings` (`core/config.py`). Fails fast on missing required vars.

| Category | Key vars | Required |
|----------|----------|----------|
| App | `DEBUG`, `ALLOWED_ORIGINS` | No |
| DB | `DATABASE_URL` | No (default: local) |
| Redis | `REDIS_URL` | No (default: local) |
| JWT | `JWT_SECRET_KEY` | **Yes** (min 32 chars) |
| Storage | `STORAGE_ENDPOINT`, `_ACCESS_KEY`, `_SECRET_KEY`, `_BUCKET` | No (default: local MinIO) |
| Vision | `VISION_PROVIDER`, `VISION_MODEL`, `OLLAMA_BASE_URL` | No (default: tesseract) |
| LLM | `LLM_PROVIDER`, `LLM_MODEL`, `ANTHROPIC_API_KEY` | No (needed for RAG) |
| Upload | `MAX_FILE_SIZE_MB` | No (default: 10) |
| ChromaDB | `CHROMA_HOST`, `CHROMA_PORT` | No (default: localhost:8000) |
| Reset | `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | No (default: 15) |

---

## 13. Deployment

### Dev
```bash
make setup   # first time: deps, .env, services, migrate, seed
make dev     # daily: API + worker + frontend in one terminal
```

### Production
```bash
cp .env.prod.example .env.prod   # fill secrets
make prod-up                     # docker compose build + up
```

Production stack: nginx serves frontend static files + proxies `/api/`
to backend. All data stores on internal Docker network. No ports
exposed except :80.

---

## 14. Adding a new feature

1. **Schema** — `schemas/`. Follow `docs/openapi-standards.md`.
2. **Model + migration** — `models/`. `DROP TYPE` in downgrade for enums.
3. **Protocol** (if swappable) — `adapters/protocols.py`.
4. **Adapter** — `adapters/`.
5. **Repository** — `repositories/`.
6. **Service** — `services/`. Raises domain errors. Takes `actor: User`.
7. **Wiring** — `api/deps.py`. Factory + `Annotated` alias.
8. **Route** — `api/routes/`. ≤ 5 lines per handler.
9. **Error handler** — add to `_STATUS` dict if new domain error.
10. **Ruff** — `make lint` before commit. Zero `noqa`.
11. **SDK** — `make generate` from root.

**Acceptance bar**: service instantiable in a test with fakes — no Docker needed.
