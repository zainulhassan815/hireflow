# Hireflow — Claude Code Guide

AI-Powered HR Screening and Document Retrieval System using RAG. Built for HR personnel to manage documents, search/ask questions over them, screen resumes, and sync candidate emails from Gmail.

## Stack

- **Backend:** FastAPI, Pydantic v2, SQLAlchemy 2 (planned), Python 3.12, `uv`
- **Frontend:** React 19, TypeScript, Vite, Tailwind v4, shadcn/ui, `@base-ui/react`
- **Services:** PostgreSQL 15, Redis 7, ChromaDB (all via `docker-compose.yml`)
- **API contract:** OpenAPI → `openapi-ts` generated client for the frontend

## Repo layout

```
backend/          FastAPI app (core, schemas, models, services, api/routes)
frontend/        React app (pages, components, providers, hooks)
docs/            Specs + conventions (authoritative, kebab-case filenames)
  features.md    Main feature tracker — pick the next task from here
  architecture.md System architecture reference
  dev/           Per-feature planning/review/summary docs (this workflow)
docker-compose.yml
scripts/
```

## Dev commands

```bash
# Services
docker compose up -d postgres redis chromadb minio

# Backend (from backend/)
uv sync
uv run uvicorn app.main:app --reload

# Celery worker (from backend/, separate terminal)
uv run celery -A app.worker.celery_app worker --loglevel=info

# Frontend (from frontend/)
npm install
npm run dev           # vite dev server
npm run generate-api  # regenerate API client from OpenAPI
npm run lint
npm run format

# Tests (backend, from backend/)
uv run pytest
```

## Authoritative docs — consult before coding

- `docs/architecture.md` — **system architecture: layers, pipelines, data model, auth, providers** (read first)
- `docs/features.md` — ordered feature tracker (pick next `[ ]`)
- `docs/conventions.md` — naming, FastAPI patterns, React composition rules, Tailwind v4
- `docs/api-standards.md` — endpoint/tag/response conventions
- `docs/openapi-standards.md` — **schema + route checklist for self-documenting OpenAPI**
- `docs/frontend-standards.md` — component + data-fetching patterns
- `docs/srs-document.md` — functional requirements (FR01+) and use cases
- `docs/rag-architecture.md` — RAG design reference

## Workflow (strict)

Every feature follows this loop. Docs live in `docs/dev/<feature-id>/`:

1. **Pick** — choose the next `[ ]` item in `docs/features.md`. Mark it `[~]`.
2. **Plan** → write `docs/dev/<id>/01-plan.md` (scope, files to touch, API/schema changes, tests, risks).
3. **Plan review** → critique the plan in `02-plan-review.md`. Revise `01-plan.md` until approved.
4. **Implement** — code the change. No doc step.
   - Final step before leaving this stage: run `uv run ruff check --fix && uv run ruff format` (backend) and `npm run lint && npm run format` (frontend) for anything touched. Don't defer.
5. **Implementation review** → `03-implementation-review.md` — what was built vs plan, deviations, concerns. Note any ruff/lint findings.
6. **Manual test** → `04-manual-test.md` — checklist of what was exercised in the browser / curl, results, any bugs found and fixed.
7. **Commit** — single focused commit referencing the feature id (e.g. `F01: add User model + Alembic baseline`).
8. **Summary** → `05-summary.md` — short postmortem: what shipped, links to PR/commit, follow-ups, lessons. Flip the tracker entry to `[x]`.

### Conventions for dev docs

- Feature id = the `FXX` code from `features.md` (e.g. `F01`, `F22`).
- Folder name: `F01-database-layer/` (id + short slug).
- Keep docs short. Bullets > prose. Link code by `path:line`.
- Don't skip steps. If a step is trivial, write one line and move on — but leave a record.

## House rules for Claude

- **Read before writing.** Always read `docs/conventions.md` + the relevant standards doc before generating code in a new area.
- **Self-documenting API.** Every new schema and route must follow `docs/openapi-standards.md`: `Field(description=..., examples=[...])` on every field, `summary` + `description` + `responses` on every route. The OpenAPI spec is the frontend developer's only documentation.
- **Match existing patterns.** Don't introduce new libraries or abstractions without flagging it in the plan.
- **No new backend libs without mention.** SQLAlchemy, Alembic, bcrypt, langchain, etc. each need to appear in the feature plan.
- **No mock data in committed code** past F02. Frontend pages should call the real API.
- **Security defaults:** never commit secrets, never weaken CORS/auth to make tests pass, fail-fast on missing env vars.
- **Scope discipline:** implement only what the current feature covers. Park unrelated fixes in a "follow-ups" list in the summary.
