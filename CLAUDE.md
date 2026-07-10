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
  features.md    Frozen roadmap snapshot — live tracking is GitHub Issues
  architecture.md System architecture reference
  dev/           Archived per-feature docs (pre-Issues workflow; don't add new)
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

- **GitHub Issues** — **the single source of truth for feature planning + history** (one issue per `FXX`, milestone per phase). Pick the next open issue; plan/reviews/summary live on it. See Workflow below.
- `docs/architecture.md` — **system architecture: layers, pipelines, data model, auth, providers** (read first)
- `docs/features.md` — frozen roadmap snapshot / dependency ordering (live status lives in Issues, not the checkboxes)
- `docs/conventions.md` — naming, FastAPI patterns, React composition rules, Tailwind v4
- `docs/api-standards.md` — endpoint/tag/response conventions
- `docs/openapi-standards.md` — **schema + route checklist for self-documenting OpenAPI**
- `docs/frontend-standards.md` — component + data-fetching patterns
- `docs/frontend-api-rules.md` — **strict rules for frontend ↔ backend wiring** (SDK types only, no mock data, no custom types)
- `docs/srs-document.md` — functional requirements (FR01+) and use cases
- `docs/rag-system.md` — **current-state RAG architecture: retrieval, intent classification, prompt composition, streaming, observability, failure modes** (read when touching `RagService`, `IntentClassifier`, `rag_prompts.py`, `/rag/*` routes, or answer-rendering components)
- `docs/rag-architecture.md` — RAG design reference (intent/rationale; predates F81)
- `docs/rag-pipeline.md` — low-level ingestion pipeline diagrams + re-index flows
- `docs/search-hardening.md` — search edge-case catalog + P0–P3 roadmap

## Workflow (strict)

**GitHub Issues are the single source of truth.** Every feature is one issue (`FXX · name`, milestone = phase). Plan, reviews, manual-test notes, and the summary all live on the issue as comments — **no `docs/dev/<id>/` folders** (those are archived). The loop:

1. **Pick** — take the next open issue (lowest-phase milestone first; honor the dependency order in `docs/features.md`). Claim it and mark it active:
   `gh issue edit <n> --add-label in-progress` (and `--add-assignee @me`).
2. **Plan** — post the plan as an issue comment: scope, files to touch, API/schema changes, tests, risks. For a large feature, promote it into the issue body under a `## Plan` heading.
   `gh issue comment <n> --body-file plan.md`
3. **Plan review** — post a plan-review comment critiquing the plan. Revise the plan until approved.
4. **Implement** — code the change. No doc step.
   - Final step before leaving this stage: run `uv run ruff check --fix && uv run ruff format` (backend) and `npm run lint && npm run format` (frontend) for anything touched. Don't defer.
5. **Implementation review** — post a comment: what was built vs plan, deviations, concerns, ruff/lint findings.
6. **Manual test** — post a comment: checklist of what was exercised in the browser / curl, results, any bugs found and fixed.
7. **Commit** — single focused commit referencing the issue (e.g. `F45: signal review (#27)`). Put `Closes #<n>` in the commit body or PR so merge auto-closes the issue.
8. **Summary + close** — post a summary comment (what shipped, commit/PR links, follow-ups, lessons), remove `in-progress`, and close the issue: `gh issue close <n> --reason completed`.

Sub-slices (`F45.c`, `F81.a–j`) are checklist items in the parent issue body — tick them as they land. Only split one into its own issue if it grows large enough to warrant a separate plan.

### Conventions for issue tracking

- One issue per top-level feature; title `FXX · short name`; milestone = phase; labels `phase:N` (+ `in-progress` while active).
- Keep comments short. Bullets > prose. Link code by `path:line`, commits by sha.
- Don't skip steps. If a step is trivial, one line on the issue is fine — but leave the record.
- `docs/dev/<id>/` is retired: historical folders stay as an archive; don't create new ones.

## House rules for Claude

- **Read before writing.** Always read `docs/conventions.md` + the relevant standards doc before generating code in a new area.
- **Self-documenting API.** Every new schema and route must follow `docs/openapi-standards.md`: `Field(description=..., examples=[...])` on every field, `summary` + `description` + `responses` on every route. The OpenAPI spec is the frontend developer's only documentation.
- **Match existing patterns.** Don't introduce new libraries or abstractions without flagging it in the plan.
- **No new backend libs without mention.** SQLAlchemy, Alembic, bcrypt, langchain, etc. each need to appear in the feature plan.
- **No mock data in committed code** past F02. Frontend pages should call the real API.
- **Security defaults:** never commit secrets, never weaken CORS/auth to make tests pass, fail-fast on missing env vars.
- **Scope discipline:** implement only what the current feature covers. Park unrelated fixes in a "follow-ups" list in the summary.
- **Comments earn their place.** Code is self-documenting by default; a comment only survives if it explains something the code cannot.
  - **Do write:** a non-obvious *why* — hidden constraint, subtle invariant, vendor/browser quirk, workaround with a link, security/correctness warning, ordering requirement, perf trick that isn't visible in the code.
  - **Don't write:** restatements of the next line, section banners (`# ---- Foo ----`, `/* ---- UI ---- */`), JSX labels (`{/* Header */}`, `{/* Status + actions */}`), docstrings that just re-say the function/class name, speculative TODOs ("lift to URL later"), refactor history ("Previously this lived in X; moved here"), or persona/user narrative ("Priya does Y daily").
  - **No feature-id tags** (`F44.b — …`, `(F93.e)`, `F89.c` prefixes) in code or docstrings. The commit message + the tracking issue (`#NN`) are the durable record; source-tree tags rot. Pydantic field/class docstrings and FastAPI route `summary`/`description` are still required per `docs/openapi-standards.md` — write them as plain contracts, without the `FXX —` prefix.
  - **Rule of thumb:** if deleting the comment would not confuse a future reader, delete it. If it *would*, keep it and make the *why* explicit.
