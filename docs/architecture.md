# System Architecture

Reference for how Hireflow's backend is structured. Read this before
touching any backend code.

---

## 1. Infrastructure topology

```
┌────────────┐   HTTP    ┌────────────┐   async   ┌──────────────┐
│  Frontend   │ ────────→ │  FastAPI    │ ────────→ │  PostgreSQL  │
│  (React)    │ ←──────── │  (uvicorn)  │ ←──────── │  (SQLAlchemy)│
└────────────┘           └─────┬──────┘           └──────────────┘
                               │                          ↑
                    enqueue    │                     sync │
                    ┌──────────▼──────────┐               │
                    │  Redis              │          ┌────┴─────────┐
                    │  • Celery broker    │          │  Celery      │
                    │  • JWT revocation   │ ◄────────│  Worker      │
                    │  • Reset tokens     │          │  (sync DB)   │
                    └─────────────────────┘          └──────┬───────┘
                                                           │
                                                    ┌──────▼───────┐
                                                    │  MinIO (S3)  │
                                                    │  blob store  │
                                                    └──────────────┘
```

| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL 15 | 5432 | Users, documents, metadata (SQLAlchemy async) |
| Redis 7 | 6379 | Celery broker/backend, JWT denylist, reset tokens |
| MinIO | 9000 (API), 9001 (console) | Document blob storage (S3-compatible) |
| ChromaDB | 8000 | Vector embeddings (Phase 3) |

All services run via `docker-compose.yml`. MinIO includes a one-shot `minio-setup` container that creates the `hireflow-documents` bucket on first boot.

---

## 2. Layered architecture

```
app/
├── domain/          ← pure business rules, no infra imports
├── models/          ← SQLAlchemy ORM
├── schemas/         ← Pydantic request/response DTOs
├── repositories/    ← data access (one class per aggregate)
├── adapters/        ← Protocol definitions + concrete implementations
├── services/        ← application orchestration
├── api/             ← HTTP layer (routes, deps, error handlers)
├── worker/          ← Celery tasks
└── core/            ← cross-cutting (config, db, redis)
```

### Layer rules

| Layer | May import | Must NOT import |
|-------|-----------|-----------------|
| `domain/` | stdlib only | anything infra, FastAPI, SQLAlchemy |
| `models/` | stdlib, sqlalchemy, `domain/` | services, routes, adapters |
| `schemas/` | stdlib, pydantic, `models/` (enums only) | services, routes |
| `repositories/` | `models/`, `domain/`, sqlalchemy | services, routes, adapters |
| `adapters/` | `core/`, stdlib, 3rd-party clients, `adapters/protocols` | services, repositories, routes |
| `services/` | `repositories/`, `adapters/` (Protocols only), `domain/` | routes, FastAPI, HTTPException |
| `api/routes/` | `services/`, `schemas/`, `api/deps` | sqlalchemy, adapters (concrete), repositories |
| `worker/tasks` | `services/`, `adapters/`, `core/` | routes, FastAPI |

**Key invariant:** services never import FastAPI or HTTPException. They raise `DomainError` subclasses; the error handler in `api/error_handlers.py` translates them to HTTP status codes.

---

## 3. Domain layer

### Exceptions (`domain/exceptions.py`)

All expected, user-facing errors. Services raise these; `api/error_handlers.py` maps them to HTTP responses in one place.

| Exception | HTTP | When |
|-----------|------|------|
| `InvalidCredentials` | 401 | Wrong email/password |
| `InvalidToken` | 401 | Expired/revoked/malformed JWT or reset token |
| `AccountDisabled` | 403 | User exists but `is_active=False` |
| `Forbidden` | 403 | Role/ownership check failed |
| `NotFound` | 404 | Resource doesn't exist |
| `EmailAlreadyRegistered` | 409 | Duplicate registration |
| `FileTooLarge` | 413 | Upload exceeds `MAX_FILE_SIZE_MB` |
| `UnsupportedFileType` | 415 | MIME type not in allowed set |

### Authorizer (`domain/authorization.py`)

Business-level permission checks. Called from services so the policy holds regardless of entry point (HTTP, CLI, worker). Methods raise `Forbidden` on denial.

```python
Authorizer.ensure_can_manage_users(actor)  # raises Forbidden if not admin
```

The HTTP-layer `require_role()` dependency in `api/deps.py` provides defense-in-depth. Both exist; neither is redundant.

---

## 4. Adapter layer

### Protocols (`adapters/protocols.py`)

One Protocol per swappable collaborator. Single-implementation things (repositories) don't get a Protocol.

| Protocol | Implementations | Purpose |
|----------|----------------|---------|
| `PasswordHasher` | `Argon2Hasher` | Hash/verify passwords |
| `TokenIssuer` | `JwtTokenIssuer` | Issue/decode JWT access + refresh tokens |
| `RevocationStore` | `RedisRevocationStore` | Denylist refresh JTIs (TTL = remaining token life) |
| `ResetTokenStore` | `RedisResetTokenStore` | One-time password-reset tokens (SHA-256 hashed) |
| `EmailSender` | `LoggingEmailSender` | Send emails (dev stub → swap for SES/SMTP) |
| `BlobStorage` | `MinioBlobStorage` | Object storage (MinIO → swap endpoint for S3/GCS) |
| `VisionProvider` | `ClaudeVisionProvider`, `OllamaVisionProvider`, `TesseractVisionProvider` | OCR for scanned PDFs and images |
| `DocumentClassifier` | `RuleBasedClassifier`, `LlmClassifier`, `CompositeClassifier` | Classify documents + extract metadata |
| `TextExtractor` | `PdfExtractor`, `DocxExtractor`, `ImageExtractor`, `CompositeExtractor` | Extract text from files |

### Shared data objects (frozen dataclasses)

| Name | Fields | Used by |
|------|--------|---------|
| `TokenPayload` | `sub`, `jti`, `type`, `exp`, `extra`, `remaining_ttl_seconds` | TokenIssuer, SessionService |
| `StoredBlob` | `key`, `size`, `etag` | BlobStorage, DocumentService |
| `ExtractionResult` | `text`, `page_count` | TextExtractor, ExtractionService |
| `ClassificationResult` | `document_type`, `confidence`, `metadata` | DocumentClassifier, ExtractionService |

### Vision provider system (`adapters/vision/`)

Runtime-selectable OCR via `VISION_PROVIDER` config:

| Value | Provider | Requires | Use case |
|-------|----------|----------|----------|
| `claude` | Claude API vision | `ANTHROPIC_API_KEY` | Best accuracy, SaaS OK |
| `ollama` | Local multimodal (LLaVA etc.) | Ollama running | Air-gapped / budget |
| `tesseract` | Tesseract OCR | `tesseract-ocr` system package | Simple docs, no network |
| `none` | No-op | — | Skip OCR entirely |

`adapters/vision/registry.py::get_vision_provider(settings)` resolves the provider. Called at Celery task execution time (not import time) so switching is runtime-dynamic.

### Classifier system (`adapters/classifiers/`)

Two-stage classification pipeline:

1. **`RuleBasedClassifier`** — keyword density for document type (resume/report/contract/letter/other). Regex patterns extract skills, experience years, education, emails, phones from resumes. Free, instant.

2. **`LlmClassifier`** — Claude or Ollama fallback. Sends extracted text with a structured JSON prompt. Parses response tolerantly (handles markdown fences, malformed JSON).

3. **`CompositeClassifier`** — rule-based first. If confidence < 0.4, tries LLM. Picks the higher-confidence result.

`adapters/classifiers/registry.py::get_document_classifier(settings)` builds the chain. LLM fallback only wired when `VISION_PROVIDER` is `claude` or `ollama`.

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
├── owner_id        UUID FK→users.id ON DELETE CASCADE INDEX
├── filename        VARCHAR(512)
├── mime_type       VARCHAR(128)
├── size_bytes      BIGINT
├── storage_key     VARCHAR(1024) UNIQUE
├── status          ENUM(pending, processing, ready, failed) INDEX
├── document_type   ENUM(resume, report, contract, letter, other) NULLABLE
├── extracted_text  TEXT NULLABLE
├── metadata        JSONB NULLABLE
├── created_at      TIMESTAMPTZ DEFAULT now()
└── updated_at      TIMESTAMPTZ DEFAULT now()
```

All models inherit `UUIDPrimaryKeyMixin` (uuid4 PK) + `TimestampMixin` (server-default `now()`, `onupdate=now()`).

Migrations managed by Alembic (async, autogenerate). `alembic/env.py` reads DB URL from `Settings`, enables `compare_type` + `compare_server_default`. Downgrade scripts explicitly `DROP TYPE` for PG enums.

---

## 6. Authentication system

### Token lifecycle

```
Register → Login → Access Token (30m) + Refresh Token (7d)
                        │                      │
                    use on /api/*           POST /auth/refresh
                        │                      │
                   401 on expiry         revoke old, issue new pair
                        │                      │
                 auto-refresh (FE)        rotation prevents reuse
```

- **Access token**: short-lived JWT (`type=access`), carries `sub` (user UUID), `role`, `jti`
- **Refresh token**: long-lived JWT (`type=refresh`), carries `sub`, `jti`
- **`decode()` enforces the `type` claim** — a refresh token cannot be used where access is expected, and vice versa
- **Rotation**: `/auth/refresh` revokes the presented refresh token's JTI in Redis, issues a new pair. Prevents stolen-token reuse.
- **Logout**: revokes the refresh token's JTI. Idempotent for undecodable input.
- **Redis denylist**: key `revoked_jti:<uuid>` with TTL = remaining token lifetime. Auto-expires; no cleanup job.

### Password security

- **Argon2id** (OWASP recommended) via `argon2-cffi` library defaults
- **Transparent rehash on login**: if `needs_rehash()` returns true (params tightened), the hash is upgraded automatically
- **Timing-safe for missing users**: `authenticate()` still calls `verify()` against a dummy hash so the latency doesn't reveal whether an email is registered
- **Password reset**: opaque token (`secrets.token_urlsafe`), stored as SHA-256 hash in Redis with 15-minute TTL. Single-use via atomic `GET+DEL` pipeline.

---

## 7. Document processing pipeline

```
Upload (POST /documents)
    │
    ▼
Store blob in MinIO → Create DB row (status=pending) → Return 201
    │
    ▼
Celery task: extract_document_text.delay(doc_id)
    │
    ▼
Worker picks up task
    │
    ├─ 1. Fetch blob from MinIO (sync)
    ├─ 2. Extract text
    │      ├─ PDF: PyMuPDF (text pages) + VisionProvider (scanned pages < 50 chars)
    │      ├─ DOCX: python-docx
    │      └─ Image: VisionProvider directly
    ├─ 3. Classify document
    │      ├─ RuleBasedClassifier (keyword density + regex)
    │      └─ LlmClassifier fallback (if confidence < 0.4 and LLM configured)
    ├─ 4. Update DB: extracted_text, document_type, metadata, status=ready
    │
    ▼
Document ready for search/RAG (Phase 3)
```

**Status transitions**: `pending → processing → ready | failed`

**Retry policy**: 3 retries, 30s delay, `acks_late=True`. Permanent failures (corrupt file, unsupported format) set `status=failed` without retrying.

**Metadata JSONB** (populated for resumes):
```json
{
  "page_count": 2,
  "skills": ["python", "react", "docker"],
  "experience_years": 7,
  "education": ["Master's"],
  "emails": ["alice@example.com"],
  "phones": ["+1 555-1234"],
  "classification_confidence": 0.68
}
```

---

## 8. Composition root (`api/deps.py`)

Single file that wires concrete adapters to Protocol abstractions and builds services. Every route reaches for things through `Annotated` aliases defined here.

```python
# Singletons (stateless, created once at import time)
_hasher = Argon2Hasher()
_token_issuer = JwtTokenIssuer(...)
_email_sender = LoggingEmailSender()
_blob_storage = MinioBlobStorage(...)

# Provider functions (called per-request by FastAPI's DI)
def get_auth_service(users, hasher) -> AuthService
def get_session_service(users, tokens, revocation) -> SessionService
def get_password_reset_service(users, hasher, tokens, email) -> PasswordResetService
def get_document_service(documents, storage) -> DocumentService
def get_user_service(users) -> UserService

# Annotated aliases for routes
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
# ... etc
```

**Swapping an implementation** = change one line in `deps.py`. Example: replace `LoggingEmailSender()` with `SesEmailSender(region="us-east-1")`.

---

## 9. API surface

All routes under `/api`. Tags map 1:1 to frontend SDK services.

### Auth (`/api/auth`)
| Method | Path | Summary | Auth |
|--------|------|---------|------|
| POST | `/register` | Register a new account | — |
| POST | `/login` | Log in | — |
| POST | `/refresh` | Refresh tokens | — |
| POST | `/logout` | Log out | — |
| POST | `/forgot-password` | Request password reset | — |
| POST | `/reset-password` | Reset password | — |
| GET | `/me` | Get current user | Bearer |

### Documents (`/api/documents`)
| Method | Path | Summary | Auth |
|--------|------|---------|------|
| POST | `/` | Upload a document | Bearer |
| GET | `/` | List my documents | Bearer |
| GET | `/{id}` | Get document metadata | Bearer (owner/admin) |
| GET | `/{id}/metadata` | Get classification + extracted metadata | Bearer (owner/admin) |
| GET | `/{id}/download` | Download file bytes | Bearer (owner/admin) |
| DELETE | `/{id}` | Delete document + blob | Bearer (owner/admin) |

### Users (`/api/users`)
| Method | Path | Summary | Auth |
|--------|------|---------|------|
| GET | `/` | List all users | Bearer (admin) |

---

## 10. Frontend integration

```
backend OpenAPI spec
    → scripts/export_openapi.py (dumps JSON without running server)
        → hey-api/openapi-ts generates TypeScript SDK
            → frontend imports from @/api

npm run generate-api  # runs both steps
```

- `src/api/client.ts` — configured fetch client with base URL from `VITE_API_URL`, request interceptor for `Authorization: Bearer`, response interceptor for 401 → auto-refresh (single-flight)
- `src/providers/auth-provider.tsx` — manages auth state, calls real SDK methods
- Generated SDK methods have JSDoc from `Field(description=...)` annotations

---

## 11. Configuration

All settings in `core/config.py` via `pydantic-settings`. Read from env vars and `.env` file. Fails fast on import if required vars are missing.

| Category | Key vars | Required |
|----------|----------|----------|
| App | `DEBUG`, `ALLOWED_ORIGINS` | No (has defaults) |
| DB | `DATABASE_URL` | No (default: local postgres) |
| Redis | `REDIS_URL` | No (default: localhost:6379) |
| JWT | `JWT_SECRET_KEY` | **Yes** (min 32 chars) |
| Storage | `STORAGE_ENDPOINT`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, `STORAGE_BUCKET` | No (defaults: local MinIO) |
| Vision | `VISION_PROVIDER`, `VISION_MODEL`, `OLLAMA_BASE_URL` | No (default: tesseract) |
| LLM | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | No (needed when used) |

---

## 12. Adding a new feature

Follow the checklist from `docs/features.md`. For code:

1. **Schema** — request/response DTOs in `schemas/`. Follow `docs/openapi-standards.md`.
2. **Model + migration** — in `models/`. Run `alembic revision --autogenerate`. Add explicit `DROP TYPE` in downgrade for new enums.
3. **Protocol** (if the feature needs a swappable collaborator) — in `adapters/protocols.py`.
4. **Adapter** — concrete implementation in `adapters/`.
5. **Repository** (if new DB aggregate) — in `repositories/`.
6. **Service** — in `services/`. Takes repos + protocols in constructor. Raises domain errors. Takes `actor: User` parameter for authorized operations.
7. **Composition root** — add provider + factory + `Annotated` alias in `api/deps.py`.
8. **Route** — thin wrapper in `api/routes/`. ≤ 5 lines per handler. `summary`, `description`, `responses` on every decorator.
9. **Error handler** — if new domain error, add to `_STATUS` dict in `api/error_handlers.py`.
10. **Ruff** — `uv run ruff check --fix && uv run ruff format` before commit. Zero `noqa`.
11. **Regenerate SDK** — `npm run generate-api` from `frontend/`.

**Acceptance bar for a service class**: instantiable in a test with fakes passed in — no Docker, no Redis, no MinIO needed.
