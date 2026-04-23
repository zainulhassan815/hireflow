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

- [x] **F44 · Candidate shortlisting (minimal)** — F42 marked "Shortlist /
  reject actions" done, but it was only half-built: the `Application`
  model + `PATCH /applications/{id}/status` endpoint exist, and the
  orphan `resume-viewer.tsx` component has `onShortlist` / `onReject`
  props — but nothing on any page imports it, and HR users have no way
  to move a candidate from `new` → `shortlisted` in the UI. Two auth
  holes confirmed by pre-F44 survey: `PATCH
  /applications/{id}/status` AND `GET /candidates/jobs/{id}/applications`
  both skip the owner check. F93 Kanban is the richer long-term shape;
  F44 is the MVP that closes the gap today.
  - [x] **F44.a** Backend: authorize `PATCH /applications/{id}/status`
    **and** `GET /candidates/jobs/{id}/applications` so the caller
    must own the application's parent job (mirrors
    `DocumentService._ensure_access`). 404 on miss or cross-tenant
    (hides existence). Admin bypass unchanged. Repository grows
    `get_with_job(application_id)` that eager-loads the job for the
    auth check — one round-trip. Tests cover unauth / missing /
    cross-tenant / admin-bypass / valid-transition for both endpoints.
  - [x] **F44.b** Frontend: new job detail page at `/jobs/:id` with
    header (title, status badge, required skills, edit/delete) and
    a candidate list body. Each row renders: name (link to source
    resume via `/documents/:source_document_id` when present), match
    score as a 0–100 bar with cat-semantic color, status badge, and
    inline action buttons — `[Shortlist]` / `[Reject]` when status is
    `new`; `✓ Shortlisted` / `✗ Rejected` + `[Undo]` for already-
    triaged rows; read-only badge for `interviewed` / `hired` (F93
    owns those transitions). Optimistic mutation via
    `onMutate` + `onError` rollback. Filter toolbar: search by
    name/email/skill, min-score slider, status multi-select.
    Routing restructure: `/jobs/:id` is the new detail route;
    `/jobs/:id/edit` stays for the edit form but is now reachable
    via a button on the detail page, not as the primary jobs-grid
    destination. `resume-viewer.tsx` deleted outright — the
    `/documents/:id` page (F105.e) is the single viewer path now.
  - [x] **F44.c** Polish follow-ups: (1) "Run match" button on the
    empty-state + persistent "Refresh scores" button in the header,
    both wired to `POST /jobs/:id/match` with list invalidation on
    success — a zero-candidate job is now one click away from a
    populated table. (2) Sortable columns (Candidate / Match score /
    Updated); click to toggle direction, score-desc is the default
    triage order. (3) Row checkboxes + header select-all with
    indeterminate state; selecting rows reveals a sticky bulk toolbar
    with Shortlist-all / Reject-all. No bulk backend endpoint — the
    frontend fans out N PATCHes with optimistic cache updates and
    rolls the whole batch back on ANY failure (partial success is
    worse UX than "redo it"). Interviewed/hired rows inside a
    selection are skipped with a count; F93 Kanban owns those.
    Relative-time column uses `date-fns` `formatDistanceToNow`
    (already in deps) rather than a hand-rolled helper.

- [~] **F44.d · Candidate triage UX rework** — F44.c shipped working
  but cluttered. The detail page has three control shapes fighting
  in the filter bar (input + native range slider + 6 pills + count),
  tall rows, and a three-button header. Rewriting against
  established ATS / issue-tracker patterns (Linear, Lever,
  Greenhouse, Notion) to get a clean triage surface that doesn't
  overwhelm. Reordered items below match the intended ship sequence
  — (1) kills the loudest visual noise, (6) unlocks daily velocity.
  - [ ] **F44.d.1** Filter rework. Replace native range slider with
    four tier buttons (`All / ≥60% / ≥75% / ≥90%`) — matches the way
    HR actually thinks about match quality and the color bands
    already used on the score bar. Status pills collapse into a
    single multi-select popover (checkboxes) so combinations like
    "shortlisted + interviewed" are possible. Active filters render
    as removable chips below the search bar (Linear / GitHub
    pattern). Single compact row: `[search] [filter popover]
    [view toggle]`.
  - [ ] **F44.d.2** Row density + always-visible actions. Compact
    rows: name primary, email muted inline (not below), 3 skill
    chips + overflow count, smaller match bar (96px), status
    shown via dot + label. Shortlist/Reject/Undo buttons stay
    visible at rest — hover-reveal was too disorienting for
    first-time users and doesn't exist on touch. Drop the
    "Updated" column; move relative time to a hover tooltip on
    the name. Zero-score bar reads as 0% (drop the 2% floor).
  - [ ] **F44.d.3** Header overflow menu + view toggle.
    Refresh scores stays primary. Edit + Delete collapse into a
    `···` overflow dropdown. Segmented `[List | Kanban]` control
    top-right — Kanban disabled with "Coming in F93" tooltip.
    Lays the track for the kanban swap so F93 is a new renderer,
    not a new page.
  - [x] **F44.d.4** Quick-peek slide-over drawer. Click a row →
    right-side drawer (~768px, vaul-backed) opens with: candidate
    header (avatar, name, email), status label + inline action
    buttons, match-score bar (larger, with bold number), skills,
    and the embedded F105 `DocumentViewer` for the candidate's
    source resume (or a "No resume on file" fallback). "Open full
    page" link navigates to `/documents/:id` for focused reading.
    Drawer's status mutation writes to the same
    `listJobApplications` cache so the list underneath updates in
    sync. Escape closes (vaul default). Row activation is click or
    Enter/Space (role=button + tabIndex=0 for keyboard users).
    Clicks on the checkbox and action-button columns
    stopPropagation so they don't also open the drawer. Drawer
    content mirrors the freshest row from the list cache on each
    render, so bulk actions / refresh-scores / row-level flips
    stay in sync while the drawer is open. Keyboard row-to-row
    nav (`j/k`) is separate — that's F44.d.5.
  - [x] **F44.d.5** Keyboard shortcuts: `j/k` (or `↓/↑`) navigate
    rows; `Enter` opens drawer for the focused row; `Esc` closes
    drawer or blurs search; `s/r/u` shortlist/reject/undo on the
    focused or drawer-current row; `x` toggles selection; `/`
    focuses the search input. Inside the drawer `j/k` advances to
    the next/previous candidate without closing — drawer stays
    open, body re-renders against the new row. Drawer state was
    lifted into `JobCandidateList` so the keyboard handler and
    drawer share the sorted/filtered view. A small `⌨` popover
    in the filter bar surfaces the shortcut list (Kbd primitive).
    Shortcuts no-op when any modifier is held or when an input is
    focused, so native browser shortcuts and typing stay intact.
  - [x] **F44.d.6** Match-score breakdown popover. Persisted the
    per-signal split (`skill_match` / `experience_fit` /
    `vector_similarity`) alongside the score on the `applications`
    table as a new `match_breakdown` JSONB column (migration
    `e6c82d9a1f44`). `MatchingService` now writes it on every
    create/update — idempotent with the rest of the scoring loop.
    `ApplicationResponse` exposes it as an optional `breakdown`
    field via `validation_alias="match_breakdown"` (null for
    pre-F44.d.6 rows until the job is re-matched). Frontend:
    hovering the list's match bar opens a `HoverCard` with a
    per-signal breakdown — label, percentage, weighted
    contribution, and a mini-bar per component. Same breakdown
    renders inline inside the drawer's match-score section (no
    hover needed there — the drawer has the space for it).
  - [x] **F44.d.7** Bulk-status endpoint: `PATCH /candidates/
    applications/bulk-status` accepts `{application_ids, status}` and
    applies in a single transaction (min 1, max 200 ids;
    `BulkUpdateApplicationStatusRequest`). All-or-nothing semantics —
    if any id is missing or cross-tenant, the whole batch rejects
    (404 / 403) and nothing is mutated. Request dedupes duplicate
    ids; response preserves request order. Owner scope is enforced
    per-application via `app.job.owner_id` before any write.
    `CandidateService.bulk_update_application_status` +
    `ApplicationRepository.list_by_ids` / `save_many` (single
    commit). Frontend `BulkActionBar` now fires one call instead of
    the previous `Promise.allSettled` fan-out — rollback is simpler
    (either the whole request failed or it didn't). 7 new tests
    covering unauth / empty list / missing id / owner happy path /
    cross-tenant 403 / admin bypass / request dedup. Full suite 460
    passing.
  - [x] **F44.d.8** Saved filter views stored in
    `hireflow.candidate-saved-views` localStorage — shared across
    jobs because the recipes (≥75% score + status=new, etc.) are
    job-agnostic. A new "Views" popover sits next to Filter and
    lists saved views with click-to-apply + hover-delete. The
    footer has a "Save current view" input that's disabled when
    no filter is active (forces users to set criteria first).
    Save / delete persist synchronously via
    `window.localStorage.setItem`; quota / Safari-private throws
    swallow silently so the UI stays functional. View shape
    (`{id, name, search, scoreTier, statusSet, sortKey, sortDir}`)
    versionless today; if the shape ever evolves, migrate by
    skipping views that don't decode cleanly. Migration to
    backend persistence is a flip-and-backfill — no per-user
    complications yet.
  - [ ] **F44.d.9** Row virtualization (pairs with F95). Flat
    performance past 500 rows. Not needed today.
  - [ ] **F44.d.10** Activity trail per application: expandable
    inline "shortlisted by X · 2 days ago" history. Needs an
    application-scoped activity-log query or a dedicated
    `application_events` table.

### Shortlisting quality track (F45 + F46 + F48)

F45, F46, and F48 are closely related and ship as a track. F45 tunes
the existing signals, F46 adds a new signal (credentials) backed by
attached files, and F48 productionizes the whole matching path
(observability, edge cases, scale, fairness review). Ideally
sequence: F46.a–c (data + ingestion) → F45.a (eval harness) →
F46.d (credential signal) → F45.b (weight tuning) → F46.e/f
(UI + tests) → F48 (productionize). F45.a gates tuning and
validation for both features.

- [ ] **F45 · Shortlisting algorithm review + improvements** —
  `MatchingService._compute_score` is currently a fixed 45/20/35
  weighted sum (skills / experience / vector) with no tuning
  evidence behind the weights and no explainability. F44 just
  exposed those scores in HR's triage flow, so the quality of the
  algorithm is now directly user-visible. Compose with F83 which
  already tracks execution items (skill normalization, required-vs-
  preferred weighting, education hierarchy, etc.) and F46 (adds the
  credentials signal F45.b will tune); F45 is the **review pass**
  that produces a concrete priority list and a regression baseline.
  - [ ] **F45.a** Eval harness: build `make eval-matching` analogous
    to the RAG eval — seed a fixture corpus of (job, candidate,
    expected-rank) triples, run matching, emit ranked agreement
    metrics (Spearman, top-K agreement). Blocks tuning work so we
    can measure improvements.
  - [ ] **F45.b** Audit the current weights: 45/20/35 is a guess.
    With a live eval harness, search the 3-simplex (maybe 7 grid
    points) for the weight set that maximizes agreement with the
    fixture. Expected lift unknown; worth measuring.
  - [ ] **F45.c** Signal review: which components are pulling weight?
    Instrument `_compute_score` to log per-candidate component
    breakdowns over 100+ real queries; surface which signals
    correlate with shortlist decisions HR actually made (status
    transitions from `new` → `shortlisted`). Feeds back into weights.
  - [ ] **F45.d** Required-skill floor: current code gives partial
    credit for missing required skills (overlap fraction). Revisit
    whether a required-skill miss should zero the skill component
    or halve it — HR should decide policy; surface as a toggle.
    Pairs with F83 "required > preferred" item.
  - [ ] **F45.e** Explainability API: extend `MatchBreakdown` with a
    human-readable sentence field generated at score time ("matched
    because Stripe appears in 3 projects, 4 years in range 3–7,
    vector sim 0.82"). Backend-side explanation generation keeps
    the frontend renderer dumb. Unblocks F44.d.3.
  - [ ] **F45.f** Cold-start: candidates without extracted skills
    (resume in a weird format, extraction failed) currently score
    0 on the skill component. Surface them separately as
    "unscored" rather than burying them at the bottom of the list.
  - [ ] **F45.g** Per-job weight overrides (optional): some roles
    are seniority-driven, others skill-driven, and — once F46.d
    lands — some are credential-driven (DevOps / cloud / regulated
    industries lean heavily on certs; UX / generalist PM roles
    barely use them). Evaluate whether a per-Job `matching_weights`
    JSONB column (`{skills, experience, vector, credentials}`) pays
    for its complexity. UI: on the job form, a collapsible
    "Advanced: signal weights" block with four sliders that default
    to the global weight set. Park until F45.b shows a single
    global weight set isn't good enough and F46.d ships the fourth
    signal — per-job tuning without credentials is the narrower
    problem we already decided to skip.

- [ ] **F46 · Multi-file candidate submissions** — today a candidate
  is one resume: `Candidate.source_document_id` is a single FK and
  both the drawer and scoring pipeline assume that one doc is the
  whole story. Real submissions are a bundle — resume + certificates
  (AWS / Azure / PMP), portfolios, transcripts, cover letters — and
  the extra files carry signal that should move the match score
  (a certified AWS Solutions Architect applying to a Cloud Engineer
  role is materially stronger than the résumé alone implies). This
  feature adds the data model, ingestion, scoring integration, and
  UI for attaching and reasoning over multiple files per candidate.
  **Part of the shortlisting quality track — pairs with F45 (weight
  tuning) and F48 (productionization). See the track intro above
  F45 for sequencing.**

  - [ ] **F46.a** Data model: `candidate_attachments` join table
    (`candidate_id`, `document_id`, `role`, `created_at`) with a
    `role` enum (`resume` / `certificate` / `portfolio` / `cover_letter`
    / `transcript` / `other`). Candidate keeps `source_document_id`
    as a convenience pointer to the canonical resume row — same
    document must also exist in the join table as `role=resume` so
    downstream code has a single traversal. Alembic migration
    backfills every existing `Candidate.source_document_id` as a
    `role=resume` attachment. Unique constraint on
    `(candidate_id, document_id)` — a file is attached to a
    candidate once, but one document could in theory be shared
    across candidates (e.g. a recruiting-event batch cert PDF), so
    no uniqueness on `document_id` alone.
  - [ ] **F46.b** Upload UX (HR-side). Candidate detail / drawer
    gains an "Attachments" section with drag-drop multi-file upload
    + role dropdown per file (auto-picks based on F23 classification
    when confident, HR can override). Reuses F21's upload endpoint
    and F105 `DocumentViewer` for preview. A new endpoint `POST
    /candidates/{id}/attachments` takes a list of
    `(document_id, role)` pairs and persists them atomically;
    `DELETE /candidates/{id}/attachments/{document_id}` detaches
    (doesn't delete the underlying Document — that stays in F22's
    ownership model). Applying role=resume when one already exists
    is a 409 — HR must detach the old one first, so the
    `source_document_id` pointer stays coherent.
  - [ ] **F46.c** Ingestion coverage: every attachment flows through
    F22 extraction and F23 classification on upload (already happens
    today for any doc). F46 adds a post-extraction hook on
    `CandidateService` that merges structured signals from each
    attachment into the candidate profile — skills extracted from a
    cert PDF union into `candidate.skills`, keywords from a
    portfolio README get stashed on a new
    `Candidate.supplementary_keywords` array. Resume remains the
    source of truth for name / email / phone / experience_years; the
    other attachments contribute only to the skill / keyword bag.
    Re-running extraction on an attachment re-runs the merge
    (idempotent: set union, not list append).
  - [ ] **F46.d** Scoring integration. Add a `credential_match`
    signal to `MatchingService._compute_score`:
    `credential_match = weighted overlap between (job.required_skills
    ∪ job.preferred_skills) and skills sourced specifically from
    role∈{certificate,transcript,portfolio}`. Boost is additive on
    top of the resume-derived skill overlap so a cert that restates
    a resume skill doesn't double-count, but a cert covering a
    required skill the resume missed lifts the candidate. New
    weights: 40/20/30/10 (skills/exp/vector/credentials) as a
    starting point, re-tuned by F45.b once the eval harness is live.
    `MatchBreakdown` + `match_breakdown` JSONB gain a fourth field
    `credential_match`; `ApplicationResponse.breakdown` surfaces it
    so the hover popover and drawer can explain the new signal.
    Old applications without credential_match render as "—" until
    re-matched.
  - [ ] **F46.e** Frontend surfacing. Candidate drawer gets a tabbed
    attachment switcher (Resume · Certs · Portfolio · Other) with
    count badges — F105 `DocumentViewer` renders the active tab.
    List row shows a small paperclip + count when the candidate has
    more than just a resume, so HR can see "this is a bundle" at a
    glance. Breakdown popover adds the `credential_match` row +
    mini-bar. Candidate detail page (full route) mirrors the drawer
    layout for focused review.
  - [ ] **F46.f** Tests: attachment CRUD (owner scope, idempotent
    resume upload, detach cascading), scoring with and without
    certs, breakdown round-trip. Extend the matching eval fixture
    (F45.a) with cert-bearing candidates to confirm the new signal
    lifts the right ranks without regressing the cert-less baseline.

- [ ] **F47 · Customizable exports** — F43 shipped a one-shot CSV
  export for a job's candidates (fixed columns, no filter awareness,
  stdlib only). HR actually asks for more: "just the shortlisted
  ones in Excel with these columns, grouped by score tier." This
  feature generalizes exports across the app: pick format (CSV /
  XLSX / PDF), pick columns, respect current filter + selection
  state, and reuse the primitive across every list surface. F47.g
  lists the other surfaces that ride on this primitive so we don't
  rebuild the export dialog five times.

  Libraries: `openpyxl` (xlsx, pure-python), `reportlab` (pdf,
  permissive licence) — both flagged here per the "no new backend
  libs without mention" rule. CSV stays stdlib. No pandas.

  - [ ] **F47.a** Backend export primitive: new `ExportService`
    takes `(rows, columns, format)` → bytes + suggested filename +
    MIME type. Column spec is a list of `(key, label, formatter)`
    so the same list can emit CSV / XLSX / PDF without per-format
    bookkeeping scattered through call sites. XLSX: freeze header
    row, bold header, autofit-ish column widths, number format on
    score column so Excel treats "0.82" as a number not text. PDF:
    landscape A4, branded header (logo + job title + generated-at
    timestamp), table with zebra stripes, footer with page numbers.
  - [ ] **F47.b** Candidate export endpoint:
    `POST /jobs/{id}/applications/export` body =
    `{columns, format, scope, filters, selection_ids}`. `scope` is
    `all | filtered | selected | shortlisted`. When `scope=filtered`
    the body carries the same query-param shape the list endpoint
    uses (search, score tier, status multi-select) so the export
    exactly mirrors what HR sees on screen. Deprecates F43's
    `GET /jobs/{id}/candidates/export` in favour of the new POST
    (GET kept for one release with a 301 pointing to the docs).
  - [ ] **F47.c** Column picker UI. Dialog behind an "Export" button
    in the filter bar. Two-column checklist: candidate fields (name,
    email, phone, skills, experience_years, education) and
    application fields (status, score, skill_match,
    experience_fit, vector_similarity, credential_match, resume_url,
    updated_at, created_at). Default selection matches today's F43
    CSV columns so existing users aren't surprised. Last-used
    selection persists per user in `hireflow.export-columns`
    localStorage (same pattern as F44.d.8's saved views).
  - [ ] **F47.d** Scope selector + format radio in the export
    dialog: "Export [All filtered (N) / Selected (M) / Shortlisted
    only (K)] as [CSV / XLSX / PDF]." The scope counts reflect the
    current filter state + F44.d-era multi-select. PDF is
    per-candidate one-page for scope≤20, tabular otherwise (the
    per-candidate layout is what hiring managers actually want for
    interview panels).
  - [ ] **F47.e** Async path for large exports (>500 rows):
    Celery task + temporary signed-URL download. Small exports stay
    synchronous with a direct file response — matches how Linear /
    Notion behave. Toast with progress for the async path; link
    persists in the UI for 15 minutes.
  - [ ] **F47.f** Share scope tightening: export endpoints enforce
    owner scope (HR sees their own jobs' applications; admin
    bypasses). Cross-tenant ID in `selection_ids` → 403, whole
    request rejected. PDF exports embed a small "Prepared for
    {owner_name} · {owner_email}" line so a shared PDF is traceable
    back to who generated it.
  - [ ] **F47.g** Broader surfaces — apply the primitive to:
    (1) Documents list (CSV + XLSX with metadata: filename, type,
    size, uploaded_at, skills, owner) — compliance often asks for
    this. (2) Activity log / F60 audit trail (CSV + XLSX) — same
    compliance lens. (3) Search results (XLSX upgrade to the CSV
    already on that page). (4) RAG conversation transcripts
    (markdown stays for F92.4; add PDF for legal review). (5) Jobs
    list + aggregate stats (CSV + XLSX; "how many apps per job,
    fill rate, avg match score"). (6) Match-score report per job
    (PDF only, branded, one candidate per page, includes breakdown
    + resume excerpt) — the panel-interview handout. Each surface
    is small: a new endpoint + wiring the same export dialog.
  - [ ] **F47.h** Tests: XLSX byte integrity (open via openpyxl,
    assert headers + cell values + types), PDF smoke test
    (page count + text extraction check), unicode in names
    (mojibake guard), scope×filter×selection matrix, owner-scope
    enforcement, async-path handoff.

- [ ] **F48 · Shortlisting productionization** — F44 shipped the
  triage flow, F45 tunes the algorithm, F46 adds the credentials
  signal. F48 is the hardening pass that takes the combined
  pipeline from "works for our fixture" to "trusted by HR on real
  requisitions." Every slice is load-bearing for "production grade,
  robust, accurate." Ships after F45.b (weights tuned) and F46.d
  (credentials signal live) so observability and fairness review
  have the final algorithm to measure. Cuts across backend +
  observability + compliance, not just UI.

  - [ ] **F48.a** Idempotency + concurrency: `match_candidates_to_job`
    today is an unserialized multi-row write. Two concurrent
    refreshes on the same job race and clobber each other's
    breakdown. Add an advisory lock (postgres `pg_advisory_xact_lock`
    keyed on `job_id`) around the match pass and make
    `ApplicationRepository.create` upsert-by-(`job_id`,`candidate_id`)
    so a re-run is exactly-once per pair. Test: two parallel
    refresh calls → one wins, the other returns the winner's
    result instead of partial-writing.
  - [ ] **F48.b** Observability: every match pass emits a structured
    log line (job_id, candidate_count, duration_ms, weight_set,
    mean_score, top_score, zero_score_count) and a Prometheus
    histogram for duration. Per-candidate `_compute_score` results
    logged at DEBUG with the breakdown, gated behind a config flag
    so prod logs stay clean. Surfaces slow jobs (>5s) and
    regression in score distributions before HR notices.
  - [ ] **F48.c** Error paths: today a single candidate with a
    malformed `skills` array or a ChromaDB timeout can 500 the
    whole match pass. Wrap per-candidate scoring in a try/except
    that logs + skips + marks the `Application.score=null` with
    `match_breakdown.error` recording the failure reason. Partial
    success beats all-or-nothing for a 500-candidate job.
  - [ ] **F48.d** Performance + scale: current implementation loads
    all candidates into memory and queries ChromaDB once with
    `n_results=100`, then O(n·m) maps hits back to candidates. At
    1k+ candidates both the memory hit and the nested loop hurt.
    Batch the vector query per 50 candidates, parallelize with
    `asyncio.gather`, replace the inner loop with a
    `{doc_id: candidate_id}` dict. Target: 500 candidates in <3s
    on the dev box. Benchmark lands in CI as a regression guard.
  - [ ] **F48.e** Audit trail for status changes: every shortlist /
    reject / undo writes to `application_events` (actor_id,
    application_id, from_status, to_status, reason_text, source
    ∈ `ui | bulk | gmail | api`, created_at). Feeds F44.d.10's
    inline history + compliance "who rejected this candidate and
    when" queries. Pair with F47.g.2 export so HR can hand the
    trail over on request.
  - [ ] **F48.f** Fairness / bias review. Log demographic-adjacent
    signals per match pass (distribution of shortlisted vs non-
    shortlisted across resume-detected gender pronoun, name-origin
    heuristics — no hard classification, just distribution
    monitoring). Surface a "review fairness" panel in the admin UI
    that flags when shortlist rates for a job diverge >2 std from
    the overall applicant pool. Not a gate — a flag. Legal lens,
    not a model change.
  - [ ] **F48.g** Recruiter override + manual score lock. HR can
    pin a score override on an Application (`score_override FLOAT
    NULL`, `override_reason TEXT`, `override_by_user_id UUID`);
    subsequent re-matches don't clobber it. Status flips stay
    independent. Surfaces as a small "Lock this score" affordance
    in the drawer. Needed because sometimes HR knows something the
    algorithm can't — fresh PhD, internal referral, etc.
  - [ ] **F48.h** Compliance: GDPR/CCPA right-to-deletion. A "Delete
    candidate + all attachments + Application history" admin
    action that cascades through Candidate → candidate_attachments
    → Applications → application_events. Soft delete with a 30-day
    purge job so an accidental click is recoverable. Required
    before we can accept EU / California applicants.
  - [ ] **F48.i** Stable re-match: a re-run of `match_candidates_to_job`
    with the same inputs produces bit-identical breakdowns. Today
    vector scores can wiggle at the 4th decimal because ChromaDB
    returns in a non-deterministic order under ties. Normalize by
    sorting + rounding at persistence time and assert stability in
    tests — HR re-running the match expecting no changes shouldn't
    see scores shift by 0.01%.
  - [ ] **F48.j** Load test + SLA: k6 script hitting
    `POST /jobs/{id}/match` at 10 concurrent users across 10 jobs;
    document a target SLA (p95 < 5s for jobs ≤200 candidates) and
    land the run in CI as a nightly. Anything slower than the SLA
    is a regression.

- [ ] **F49 · Job status lifecycle** — `JobStatus` enum exists
  (`draft / open / closed / archived`, defaults to `draft`) and the
  list endpoint accepts a `status` filter, but there's no way to
  actually change a job's status: no PATCH endpoint, no UI control.
  A draft job can't be promoted to open; a filled job can't be
  closed. Status never changes in prod today. This is a small but
  real gap.

  - [ ] **F49.a** Backend: `PATCH /jobs/{id}/status` with
    `{status: JobStatus}` body. Owner-scoped (HR can change their
    own jobs' status; admins bypass) via the existing
    `_ensure_access` pattern on `JobService`. Validate transitions
    — `draft → open → closed → archived` is the happy path;
    `closed → open` is allowed (reopening a req); `archived → *`
    is blocked (archive is terminal, use a new job). Invalid
    transitions → 409 with a message the UI can surface.
  - [ ] **F49.b** Frontend: status-dropdown control in the job
    detail header, right of the title. Confirms archive with
    `AlertDialog` (per F98's confirmation-hardening pattern —
    archive is the only terminal transition). Inline toast on
    success; optimistic cache update via the
    `listJobs` + `getJob` query keys.
  - [ ] **F49.c** Jobs-list filters: add a status multi-select
    above the jobs list (reusing the candidate-filter-bar pattern
    from F93.e) so HR can focus on open reqs. Hides archived by
    default; "Show archived" toggle in the filter popover.
  - [ ] **F49.d** Lifecycle automation (opt-in per job):
    `auto_close_on_hire BOOLEAN DEFAULT FALSE` on Job. When an
    Application flips to `hired` and the job has this on, the job
    auto-transitions to `closed` and emits an audit event (F48.e).
    Small but surprisingly loved once it ships.
  - [ ] **F49.e** Tests: transition matrix (happy path + blocked
    archive → open), owner-scope enforcement on PATCH, filter
    behaviour with mixed-status seed data, auto-close trigger.

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

- [x] **F53 · Multiple Gmail accounts per user** — today one HR user can
  connect exactly one Gmail mailbox (the `gmail_connections` table has a
  `UNIQUE (user_id)` constraint; re-authorizing overwrites the token).
  HR teams run a recruiting inbox *and* personal inboxes that receive
  resumes; the product assumption of one-per-user forces them to choose.
  The sync service (`GmailSyncService.sync`) already takes a
  `connection_id`, iterates all rows in the fan-out task, and dedupes
  candidates at `(owner_id, email)` — so the business layer is already
  multi-account-capable. Only the model constraint, the upsert, the
  routes, and the UI assume one-per-user.
  - [x] **F53.a** Backend: drop `UNIQUE (user_id)`, replace with
    `UNIQUE (user_id, gmail_email)` (Alembic migration). Repository
    grows `list_by_user`, `get_by_user_and_email`, `get_for_user`
    (owner-scoped lookup by connection id); `upsert` keys on
    `(user_id, gmail_email)` so re-authorizing the same address updates
    tokens in place and a new address adds a row. Service +
    routes pluralize: `GET /gmail/connections` (list),
    `POST /gmail/connections/{id}/sync`,
    `DELETE /gmail/connections/{id}`. `POST /gmail/authorize` stays;
    callback flow unchanged (Google returns the email, upsert picks the
    row). Singular `GET /gmail` / `POST /gmail/sync` / `DELETE /gmail`
    removed — frontend moves in F53.b in the same commit window.
  - [x] **F53.b** Frontend: replace the single-status card in
    `settings/email-connection.tsx` with a per-row list (one row per
    connection: email, connected_at, last_synced_at, Sync / Disconnect
    buttons) plus a top-level "Connect another account" button.
    Regenerate the SDK after F53.a.

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

- [x] **F63 · Dev-mode logging config**
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

- [x] **F90 · Design revamp + system baseline** — full visual-identity pass.
  Kills AI-slop defaults and establishes tokens that F91–F96 inherit.
  Driven by the `/impeccable:critique` findings in
  `docs/dev/F90-design-revamp/01-critique.md` (baseline heuristic score
  23/40; post-F90 re-score **31/40**, detector **0 findings**). Executed as eight sequential `/impeccable:*` passes; each gets
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
  - [x] **F90.h** `/impeccable:polish` — final pass: pure-black backdrop
    → brand-tinted, kill bounce animation, align spacing drift, document
    the resulting tokens.

  Originally-scoped bullets fold into sub-features above:
  - spacing/typography/color consistency → F90.b + F90.c
  - dark mode verification → F90.c
  - responsive audit → F90.h
  - loading skeletons → F90.f
  - transition animations → F90.e + F90.g

- [~] **F91 · Documents page polish**
  - [x] Drag-and-drop upload zone on the main page (not just in dialog)
    — page-level overlay, drop anywhere on /documents
  - [ ] Upload progress with real percentage (needs XHR/axios
    migration from fetch; deferred)
  - [x] Document processing status: live polling every 3s while any
    doc is pending/processing, stops when all are settled
  - [ ] Inline preview for PDFs (embedded viewer) — deferred; pdf.js
    or iframe approach TBD
  - [x] Bulk actions: select (checkbox column + select-all),
    confirm-gated bulk delete. Export + "create candidates" still
    deferred (needs backend batch endpoints).

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

- [~] **F93 · Kanban board view for applications** — reached after
  F44 surfaced the list-mode triage flow; Kanban is the same data
  visualized as columns you drag between. F44's view-toggle button
  has been waiting for this renderer since F44.d.3.

  Prereq note from the old F93 entry is stale: `Job.status` already
  exists (F90 / F53), `Application.score` exists (F41), and
  `Application.match_breakdown` landed in F44.d.6. No schema work
  blocks the Kanban itself.

  - [x] **F93.a** Board view using `@dnd-kit/core` (+ `/sortable`,
    `/utilities`). Five fixed columns mirroring the status enum:
    New · Shortlisted · Interviewed · Hired · Rejected (far-right,
    visually muted). Drag a card across columns → `PATCH
    /applications/{id}/status` via the existing endpoint, cache
    patched optimistically, rollback on error (same pattern the
    row and drawer use). Cards pack the same content the list
    row shows: avatar, name link, score bar with breakdown
    hover-card, top-3 skill chips. Click card → opens the
    existing `CandidateDrawer`. `MouseSensor` requires 5px of
    movement before drag-start so a click-and-release still opens
    the drawer; `TouchSensor` has a 200ms delay so vertical scroll
    on mobile doesn't accidentally drag. `DragOverlay` renders the
    lifted card outside document flow — source column doesn't
    reflow during drag. `useDroppable` marks columns; hovering
    highlights the target column bg + border. Keyboard drag
    supported natively by dnd-kit (Tab to card, Space pick up,
    Arrows move, Space drop). Within-column reorder is out of
    scope (F93.c, needs `column_position`).
  - [x] **F93.b** WIP count per column rendered as a pill badge
    next to the column header. No hard WIP limit — just a visible
    indicator. Real WIP-limit warnings (e.g. "Shortlisted · 12/15
    — at capacity") can follow once users pick a meaningful cap.
  - [ ] **F93.c** Within-column reorder. Adds `column_position
    FLOAT NOT NULL DEFAULT 0` on Application + `PATCH
    /applications/{id}/position` endpoint. Use midpoint-between-
    neighbors trick so one drag = one UPDATE. Ship when users
    actually ask for hand-ranking.
  - [ ] **F93.d** Multi-card drag via the F44.d.7 bulk endpoint.
    Dnd-kit supports multi-drag via the `MultipleContainers`
    strategy.
  - [x] **F93.e** Filter-state lift — promoted from follow-up
    after the first user toggled to Kanban and lost the whole
    filter UI. Filter bar (search, score tier, status multi-
    select, saved views, keyboard hint, active chips) extracted
    into `candidate-filter-bar.tsx` with a shared
    `useCandidateFilters` hook + pure `applyCandidateFilters`
    reducer. Detail page owns filter state and renders the bar
    above both views; list and board each receive pre-filtered
    applications. The `[List | Kanban]` toggle slots into the
    bar's `rightSlot` prop so it stays visible across modes.
    List keeps local sort / selection / drawer / keyboard state;
    board keeps local drag / drawer state. When filters produce
    an empty result the parent renders `<EmptyFiltersState>`
    with a "Clear filters" link instead of either view.

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

- [ ] **F97 · First-use onboarding** — first-visit Priya lands on an empty
  Dashboard with an "Upload documents" CTA but no guided moment showing
  the full workflow (upload → process → search → shortlist). Post-F90
  critique scored Heuristic 10 (Help & Documentation) at 2/4 for exactly
  this reason. Peak-end rule says we're leaving a win on the table.
  - [ ] **F97.a** Scope decision: three-card inline explainer on empty
    Dashboard vs interactive guided tour vs static help panel. Cheapest
    win: inline explainer that hides once `stats.documents > 0`.
  - [ ] **F97.b** Implementation: Dashboard empty-state carousel/strip
    showing (1) upload, (2) search/ask, (3) shortlist — each with an
    illustration or icon + one sentence + CTA to that page.
  - [ ] **F97.c** Dismissal: user can skip the explainer; localStorage
    flag remembers the choice so repeat-visit empty states stay clean.
  - [ ] **F97.d** Copy pass in F90.g voice ("Upload the stack. / Search
    the way a person reads. / Keep the shortlist you can defend." is the
    starting point — each sentence maps to one onboarding step).

- [ ] **F98 · Confirmation hardening** — F90.f added AlertDialog confirms
  on single-item delete, but high-stakes paths still need more friction.
  Post-F90 critique flagged this as a P3.
  - [ ] **F98.a** Type-to-confirm on cascading deletes: deleting a Job
    with matched Candidates requires typing the job title. Same for any
    future bulk-delete action on Documents.
  - [ ] **F98.b** Logout confirm (deliberately skipped in F90.f as low-
    priority). Revisit if session loss is causing friction — likely not
    needed.
  - [ ] **F98.c** Soft-delete + Undo toast: backend supports a soft-
    delete flag (`archived_at` or similar), delete mutations set it;
    toast shows "Undo" for 5s; undo clears the flag. Applies first to
    Documents, later to Jobs.

- [ ] **F99 · Design system documentation** — F90 landed a coherent design
  system (tokens, typography, color, radius, primitive patterns) but no
  doc exists for future contributors. Without it, the next Claude session
  or new engineer won't know why `asChild` is banned, why blue is
  action-only, why `--radius-2xl/3xl/4xl` are zeroed, etc.
  - [ ] **F99.a** `docs/design-system.md` covering: token map (font /
    color / radius / spacing), primitive patterns (the `render={}`
    migration from `asChild`; why `SelectValue` bridges `placeholder`),
    voice guide (editorial-serious, second-person, no "just", no "AI"
    adjective), anti-goal list from brief §10.
  - [ ] **F99.b** Code examples for each token class (how to use
    `bg-success` vs hand-coding hex; how to use `font-display`; how to
    avoid the now-forbidden `asChild`). Runnable snippets.
  - [ ] **F99.c** "When to reach for" decision table: sharp surface vs
    rounded interactive, cat-1..5 vs semantic hues, display face vs
    sans, mono vs proportional.

- [ ] **F100 · RAG confidence label at source** — F90.f rewrote the UI
  badges (`high / medium / low` → `Strong match / Partial match / Weak
  match`) via a frontend map. The backend still emits the old enum. If
  any other consumer (logs dashboard, admin tooling, CSV export) reads
  the same field, they'll see raw `high/medium/low`.
  - [ ] **F100.a** Backend: rename the enum values in the response
    schema; add a migration for any stored values.
  - [ ] **F100.b** Frontend: delete the `CONFIDENCE_DISPLAY` translation
    map in `search.tsx`; render the backend value directly.
  - [ ] **F100.c** Contract test: search + RAG response snapshots
    updated to match new labels.

- [ ] **F102 · Keyboard-first command palette** — Linear-style command
  palette as the single global shortcut. Phase A (this feature) ships
  `⌘K` to open a searchable palette with Navigate / Create / Account
  groups. Phase B (full Linear parity — sequence shortcuts, help
  overlay, per-page contexts, hint badges) deferred until power-user
  usage is validated.
  - [x] **F102.a** `⌘K` global keydown listener in `AppLayout`
    (Cmd or Ctrl, preventDefault + toggle).
  - [x] **F102.b** `CommandPalette` component using shadcn's
    `CommandDialog`. Groups: Navigate (Dashboard / Documents / Search
    / Candidates / Jobs / Activity Logs / Settings), Create (Upload
    documents, Create job), Account (Log out). Fuzzy search via cmdk.
  - [ ] **F102.c** Discoverability: a subtle "⌘K" kbd hint in the
    sidebar footer or user row. Optional; not shipped with Phase A.
  - [ ] **F102.d (deferred, Phase B)** Sequence shortcuts: `G D`
    (Dashboard), `G F` (Files / Documents), `G S` (Search), etc. with
    1s timeout and a mid-sequence visual indicator.
  - [ ] **F102.e (deferred, Phase B)** `?` help overlay scoped to
    current page context.
  - [ ] **F102.f (deferred, Phase B)** Per-page context shortcuts
    (`J/K` list nav, `E` edit, `Esc` stop generation on chat).
  - [ ] **F102.g (deferred, Phase B)** Shortcut hint badges (`<Kbd>`)
    inline in buttons, menus, and tooltips.

- [~] **F103 · RAG indirect-evidence reasoning** — surfaced by a
  real-world query: *"do we have any candidate with stripe
  experience?"* Retrieval correctly returned a project case study
  documenting a Stripe integration; the LLM answered "Not in the
  provided documents" because the case study didn't explicitly name
  the candidate, and the candidate's resume skill-list didn't include
  "stripe" (it was buried in project narrative). The dots exist in
  the data but nothing connects them.
  - [x] **F103.a** Prompt: loosen the "Not in the provided
    documents" sentinel in `rag_prompts.EVIDENCE_RULES` so partial /
    indirect evidence is described and cited rather than deflected.
    Reserve the sentinel for genuinely off-topic retrievals.
    PROMPT_VERSION bumped v2 → v3.
  - [ ] **F103.b** Narrative skill extraction: extend the skill
    classifier to read technologies out of experience / project
    descriptions, not just explicit "Skills:" sections. Populates
    the parsed `skills` metadata so retrieval and scoring surface
    technology hits even when the candidate doesn't list them.
  - [ ] **F103.c** Author linkage: portfolio / case-study
    documents are authored by a candidate but the schema has no
    link. Infer via email-in-document ↔ candidate.email match at
    ingestion time, or add an explicit `authored_by` foreign key
    set from extraction metadata. With the link, RAG context can
    include "this document was authored by {candidate}" so Claude
    attributes project work to the right person natively.
  - [ ] **F103.d** Entity-aware contextualizer prompt: rewrite the
    `ChunkContextualizer` prompt so the per-chunk summary preserves
    authorship and first-person language. Current summaries turn
    *"I built a Stripe integration"* into *"the API server was built
    to bridge Stripe and GHL"* — stripping the agent and losing the
    retrieval signal that links chunks to people. New prompt should
    incorporate `{candidate.name}` when author is known (depends on
    F103.c for non-resume docs; resumes already have name in
    metadata) and the classifier's extracted technology list so
    stripe-in-narrative ends up in stripe-in-context.
    Requires a bump to the contextualizer prompt version and a full
    re-embed so the new summaries land in vectors. Pairs naturally
    with F103.b landing first.
  - [ ] **F103.e** Improved summarization prompt for the RAG
    answer layer (distinct from F103.d which is the chunk-level
    contextualizer). Today's prompt is a minimum viable citation
    + deflection contract. A stronger prompt would: (1) name
    candidates in the answer when context supplies a name, not
    "the candidate"; (2) prefer evidence-dense sentences over
    hedging; (3) quantify when quantities exist ("3 years of
    Stripe integration work" over "has Stripe experience"); (4)
    cross-reference docs in a single claim where the same person's
    resume + case study both speak to a skill. Writable and
    testable offline via the existing RAG eval harness once we
    stub sample queries.

- [ ] **F104 · RAG + search moonshots** — menu of improvements,
  each independently shippable, each individually meaningful.
  None locked-in as scoped; we'll revisit after F103 lands and
  pick based on where quality still feels thin. Ordered by
  rough impact-per-effort.

  **Tier 1 — prompt / small infra, large visible effect:**
  - [ ] **F104.a** Candidate one-liner at ingest: after parsing a
    resume (or linking a case study via F103.c), generate a
    one-sentence candidate summary ("Zain Ul Hassan — full-stack,
    4+ yrs, Stripe + GHL + TypeScript heavy"). Store alongside
    the candidate row and index it as a separate retrieval source.
    Queries like *"who has X?"* hit summaries before chunks —
    much higher recall with lower noise.
  - [ ] **F104.b** Query expansion / HyDE: before retrieval,
    use Haiku to rewrite the user's question into 2–3 paraphrases
    and/or a hypothetical answer. Embed each, union the
    retrievals, dedupe, rerank. Fixes the gap where the user asks
    in one vocabulary and the doc uses another.
  - [ ] **F104.c** Source diversity: the reranker top-K often
    comes from one dominant doc. Enforce "at most 2 chunks per
    doc, at least 3 docs when available" so the answer sees
    breadth. Small rule, often fixes "Claude only read Tutorelli"
    feelings.
  - [ ] **F104.d** Hallucination guard: after Claude answers,
    a second short LLM pass checks each claim against its
    cited chunk. Flag unsupported claims visibly. Builds trust
    more than anything else we could ship.

  **Tier 2 — architectural, medium cost:**
  - [ ] **F104.e** Hybrid retrieval with bge-m3 (dense + sparse):
    swap `embedding_model` to BAAI/bge-m3 and extend the
    `EmbeddingProvider` protocol to also return sparse term
    weights. Weighted RRF already exists (F85.c) — it just needs
    a sparse source to fuse against dense. Full re-embed
    required.
  - [ ] **F104.f** Named-entity extraction at ingest: NER over
    every doc to surface people, orgs, technologies, locations,
    dates as typed metadata. Powers filtered search ("candidates
    with FastAPI at startups in London, ≤ 2 yrs experience") and
    gives the reranker structured signal.
  - [ ] **F104.g** Intent-specific retrieval paths: F81.g
    classifies intent but routes everything through the same
    retriever. Different intents deserve different strategies —
    `count` queries aggregate at candidate level, `locate`
    queries need document-level recall, `comparison` needs
    top-K-per-entity. Plumb the intent into retriever selection.
  - [ ] **F104.h** Parent-document retrieval: chunk small for
    precision, retrieve big for context. Keep the current chunks
    as embed targets; when surfacing context to the LLM, expand
    each hit to its surrounding section so Claude sees more
    signal per token spent.

  **Tier 3 — ambitious:**
  - [ ] **F104.i** Agent with tools instead of single-shot RAG.
    Claude gets `search_chunks`, `get_candidate`,
    `list_candidates(filters)`, `compare_candidates(ids, attrs)`.
    For complex queries (*"rank the top 3 candidates for a senior
    backend role, explain each"*), Claude plans, calls tools,
    synthesizes. Much more flexible than single-shot RAG. Bumps
    cost per query; better UX for messy questions.
  - [ ] **F104.j** Streaming citation highlights: as tokens
    arrive, the cited source chunks pulse/highlight in real time
    in the sidebar. "Claude is reading Zain's CV right now…"
    Pure UX flex; cheap once F81.j citation parser is already
    wired.
  - [ ] **F104.k** Match-explanation hover: hovering a candidate
    card pops *"matched because Tutorelli case study mentions
    Stripe (0.23 distance, reranker score 0.89)."* Radical
    transparency about why the system ranked someone where it
    did. Trust multiplier.

- [ ] **F101 · Document thumbnails** — generate a small preview image
  per document during processing so the Documents grid view, preview
  dialog, and similar-docs list render the first page instead of a
  generic type icon. Pairs with F90.d's visual-grid instinct and
  removes a lot of "all docs look identical" noise.
  - [ ] **F101.a** Backend: add a thumbnail step to the Celery
    ingestion pipeline. PDFs → render first page via pdf2image /
    PyMuPDF; images → resize via Pillow; other types (docx, txt) →
    skip and let the frontend fall back to the type icon (MVP). Store
    in MinIO at `thumbnails/{doc_id}.webp`, 320px wide, quality ~80.
  - [ ] **F101.b** Schema: `thumbnail_path` nullable column on
    `documents`. Alembic migration. `DocumentResponse` gains a
    `thumbnail_url` computed from the signed MinIO URL (same pattern
    as `download_url`).
  - [ ] **F101.c** Frontend: Documents grid view renders the
    thumbnail at `aspect-[3/4]` with `object-cover`; fallback to the
    existing type icon when `thumbnail_url` is null or fails to
    load. Table view gets a 32×32 thumbnail next to the filename.
  - [ ] **F101.d** Preview dialog hero: show the thumbnail as the
    lead image above the "Similar documents" section when available.
  - [ ] **F101.e** Reprocess path: existing documents don't have
    thumbnails. Add an admin command (or one-shot migration) that
    queues thumbnail generation for every `status = ready` doc
    without one.
  - [ ] **F101.f** Failure handling: thumbnail generation must not
    block the `ready` state — if it errors, log + leave
    `thumbnail_path = NULL` + move on. The document is usable
    without a thumbnail.

  Open questions to settle at start:
  - Do resumes (the primary doc type) benefit from thumbnails at
    all? Resume first pages look ~identical at 320px. Maybe render a
    contact-header strip instead, or skip resumes entirely.
  - Dependencies: pdf2image needs `poppler-utils` system binary;
    PyMuPDF (`pymupdf`) is pure Python wheel. Prefer PyMuPDF for the
    thinner install.

- [x] **F105 · Hybrid document viewer (factory pattern)** (a–e all shipped) — today a
  document preview shows metadata + similar docs (F89.c.1) but no
  actual content. We want one entry point (`<DocumentViewer>`) that
  renders anything the corpus holds — PDFs, images, office files,
  spreadsheets, text — without a god-component. Factory pattern
  mirrors the existing `LlmProvider` / `EmbeddingProvider` /
  `DocumentClassifier` shape.

  **Canonical kinds** (exactly five; frontend dispatches on `kind`):
  `pdf` (iframe), `image` (`<img>`), `table` (`{sheets: [{name,
  headers, rows}]}` → TanStack Table), `text` (plain or markdown),
  `unsupported` (download fallback).

  **Backend:** `ViewerProvider` Protocol in
  `app/adapters/viewers/` with a registry; each provider declares
  `accepts(mime) -> bool` + `render(doc, blob) -> ViewablePayload`.
  `GET /documents/{id}/viewable` picks the right provider and
  returns the payload. Lazy (on-demand) for F105.a passthrough
  providers — no blob rewrite — eager (ingest-time) once
  conversion providers land in F105.c.

  **Frontend:** `<DocumentViewer payload={...}>` component with a
  one-to-one renderer map; adding a new kind is one file. Wires
  into the existing preview dialog.

  - [x] **F105.a** Foundation: `ViewerProvider` Protocol + registry +
    `PassthroughPdfProvider` (`application/pdf` → `pdf`),
    `PassthroughImageProvider` (`image/*` → `image`),
    `FallbackProvider` (anything else → `unsupported`). New endpoint
    `GET /documents/{id}/viewable` returning `ViewablePayload` (with
    signed MinIO URL for passthrough kinds). Frontend
    `<DocumentViewer>` component dispatching on `kind`; wired into
    the preview dialog. No schema change (no conversion yet, so no
    second blob to persist). Ships PDFs + images end-to-end.
  - [x] **F105.b** `OfficeToPdfProvider`: docx, pptx, odt, odp, rtf,
    doc, ppt → `pdf` via LibreOffice headless. Protocol gained a
    `prepare()` hook called from the Celery worker after extraction
    commits; `ViewerPreparationService` swallows prep failures so a
    dev machine without LibreOffice still has a working pipeline
    (office files fall through to the `conversion_pending` download
    card). Converted asset lives in MinIO at `viewable/<doc_id>.pdf`;
    new nullable `documents.viewable_kind` + `viewable_key` columns
    (migration `d82a5f4e9c18`). Backend Dockerfile adds
    `libreoffice-core` + `-writer` + `-impress` (component subset,
    not the meta-package — F105.c will append `-calc`). Spreadsheet
    MIMEs deliberately excluded — reserved for F105.c's real table
    renderer. Frontend unchanged: office files arrive as
    `kind: "pdf"` via the F105.a iframe path. 15 new tests incl.
    back-compat for pre-F105.b PDFs and idempotent re-prepare.
    Follow-ups: orphan `viewable/` blob cleanup on doc delete.
    Backfill for pre-F105.b docs ships via
    `scripts/prepare_viewables.py` (`--dry-run` / `--force` /
    `--limit N`) — calls `ViewerPreparationService.prepare` directly,
    ~60× cheaper than re-running extraction.
  - [x] **F105.c** `SpreadsheetProvider` (xlsx via `openpyxl`) +
    `CsvTsvProvider` (stdlib `csv`) → `kind=table`. Parses each
    sheet into `{name, headers, rows, truncated, total_rows,
    total_cols}`, stores the JSON at `viewable/<doc_id>.json` in
    MinIO, inlines on render. Row/col caps 10k × 100 protect the
    payload size. Frontend `<TableRenderer>` ships a sheet-tab
    strip (multi-sheet xlsx), sticky header + first column, and a
    "showing first N of M" notice when truncated. Legacy xls + ods
    out of scope; add only if asked. 19 new tests.
  - [x] **F105.d** `TextProvider` (txt, md, application/x-log) →
    `kind=text`. Source bytes decode as UTF-8 with
    `errors="replace"` so rogue bytes don't crash the response.
    5 MB inline cap — oversized text falls through to
    `unsupported` + `reason="too_large_to_inline"`. Frontend
    `<TextRenderer>` uses the existing `react-markdown` + GFM
    toolchain from F81.g for markdown, `<pre whitespace-pre-wrap>`
    for plain. text/csv deliberately NOT owned here (F105.c's
    table UX beats a raw dump). 14 new tests.
  - [x] **F105.e** `/documents/:id` page. Reuses the same
    `<DocumentViewer>` from the dialog with fuller chrome: back
    button, filename header with download button, two-column
    layout with details + similar-docs sidebar. Clicking a
    neighbour in the sidebar navigates in-place rather than
    reopening a dialog. Documents-page dropdown menu gains an
    "Open" item alongside "Preview" (dialog stays for quick
    peeks; the page is for focused reading).

- [x] **F106 · Logo, branding & PWA** — brand mark + installable app
  - [x] **F106.a** Logo: ascending 4-bar ranking chart (amber → pink
    → violet → blue, tallest bar tilted) as `logo.svg` / `favicon.svg`
    and reusable `<Logo />` component. Wired into sidebar header and
    auth layout (desktop + mobile). Old `vite.svg` / `react.svg`
    template assets removed.
  - [x] **F106.b** Per-page document titles via `useDocumentTitle`
    hook + `useRouteTitle` reader. Protected routes declare
    `handle: { title: ... }` in `router.tsx`; `AppLayout` sets
    `"<Page> · Hireflow"` on navigation. `AuthLayout` syncs its
    `title` prop to `document.title` for auth pages.
  - [x] **F106.c** PWA: `vite-plugin-pwa` + `@vite-pwa/assets-generator`;
    `pwa-assets.config.ts` sources all icon sizes from `logo.svg`
    (`npm run generate-pwa-assets`). Manifest (`name`, `theme_color`
    `#1d4ed8`, `background_color` `#fafafa`, `display: standalone`)
    and workbox SW auto-registered. `index.html` gets description,
    theme-color, Apple PWA meta, full favicon hierarchy.
  - [x] **F106.d** In-app install button: `usePwaInstall` hook
    captures `beforeinstallprompt`; `<InstallAppButton />` in the
    sidebar footer surfaces Chrome's install UI (which otherwise
    hides in the URL bar). SW enabled in `vite dev` via
    `devOptions: { enabled: true }` so install criteria are met on
    localhost without a prod build.

- [x] **F107 · Color & theme pass** — the F90 palette existed but
  lived almost exclusively on small outline badges; the rest of the
  chrome was gray. F107 pushes hue into the content (hero, icons,
  metrics, empty states, skill chips) and ships the missing
  light/dark switcher so users can pick.
  - [x] **F107.a** Color enrichment: sidebar active state → full
    primary (icon + label + `bg-primary/8` row tint, not just the
    3px rail); dashboard hero gets a `border-primary` left rule +
    primary numeral + three-hue metric strip (cat-5/cat-4/cat-2);
    filetype glyphs tint by document_type (`bg-cat-X/10 text-cat-X`)
    in documents table + grid and dashboard recent-docs; 5 empty
    states get a drop-cap tinted-square hero icon (primary /
    cat-2 / cat-4 / info); jobs page aligns status badge with the
    F90.d semantic map (bg-success on open) and gains a leading
    status dot on each card. Skill tags become pastel chips with
    a stable `skillHueClass()` hash so "Python" reads the same hue
    across candidates table, jobs cards, search-result metadata,
    candidate detail modal, and document preview. Five new
    `--cat-X-ink` tokens in `index.css` paired with `bg-cat-X/15`
    give GitHub-label-style chips: low-alpha tint, high-chroma
    same-hue text. All five ink tokens clear WCAG AA contrast in
    light and dark modes (including chartreuse, where
    full-saturation `text-cat-4` previously failed).
  - [x] **F107.b** Theme switcher: `next-themes` was already a dep
    via `sonner` but no `<ThemeProvider>` wrapped the app. Wired
    it at `main.tsx` with `attribute="class"`, `defaultTheme="system"`,
    `enableSystem`, `disableTransitionOnChange`. Three surfaces
    expose the toggle: a Theme submenu in the sidebar user
    dropdown (Light/Dark/System radio with Sun/Moon/Laptop icons),
    an Appearance card on `/settings` (segmented buttons,
    SSR-safe `mounted` flag to avoid first-paint flicker), and
    three command-palette entries under an Appearance group with
    `keywords={["theme", "light"|"dark"|"system", "appearance"]}`
    so Cmd/Ctrl+K → "dark" → Enter works. No dedicated global
    shortcut: the safe combos all collide with browser/OS
    bindings and theme is a set-once preference; the palette
    path costs three keystrokes and zero collisions.

- [x] **F108 · Document detail page polish** — F105.e landed a
  dedicated `/documents/:id` page in parallel with an in-flight
  Sheet-based preview redesign. Two paths to the same "view a
  doc" intent is worse than one polished path, so F108 deletes
  the preview Dialog entirely and routes everything to the
  detail page — row click, grid card click, and the former
  Preview dropdown item all resolve to `navigate(\`/documents/${id}\`)`.
  The page itself gets the UX that was planned for the Sheet:
  tinted header glyph (F107.a `typeIconClass`), tabbed right
  rail (**Details** / **Text** / **Similar**), pastel skill
  chips, F90.d semantic status badge, and a full-viewport
  `h-full` layout so the viewer fills its pane instead of
  bottoming out at the old 400px floor.
  - [x] **F108.a** Kill the preview Dialog + polish the detail
    page. Changes:
    (1) Delete `components/documents/document-preview.tsx` and
    all its wiring. The `previewDoc` state and the Preview
    dropdown item come out of `pages/documents.tsx`. Table row
    click and grid card click both navigate to the detail page;
    selection checkbox + actions dropdown `stopPropagation` so
    they don't trigger the row navigation.
    (2) Extract `typeBadgeClass` + `typeIconClass` to
    `lib/utils.ts` — previously duplicated between dashboard.tsx
    and documents.tsx, now a third consumer (detail.tsx) would
    have made it a rule-of-three violation.
    (3) Rewrite `pages/documents/detail.tsx`: header bar with
    back button + tinted filetype glyph + filename + size·date
    meta + Download (outline). Body is `grid-cols-[1fr_22rem]`
    on `lg:` — viewer column fills; right rail is `Tabs` with
    Details / Text / Similar. Each `TabsContent` owns its own
    scroll via `min-h-0 flex-1 overflow-auto`. Details dl uses
    uppercase tracking-wide labels (editorial-serious); skills
    use `skillHueClass` for cross-page hue consistency; Text
    tab renders extracted content without a `<pre>` (selection
    works without the old shenanigans); Similar tab hosts the
    existing neighbours panel.
  - [x] **F108.b** Layout v2 (tabs on viewer, accordion on
    sidebar). F108.a's right-rail tabs caused a visible shift
    on every tab change — the panel's content width flexed as
    the scrollbar appeared/disappeared, and three candidates
    (Details / Text / Similar) were fighting for a narrow rail.
    F108.b reshuffles: main area tabs are **Document** and
    **Text** (so Text competes for viewer-scale real estate,
    not rail-scale); right rail becomes a static Details block
    + a collapsible **Similar documents** accordion (default
    closed). `keepMounted` on the main-area tab panels keeps
    the viewer iframe alive (signed URL, scroll, zoom
    preserved across tab swaps); inactive panels use
    `data-hidden:hidden` (base-ui's `data-hidden` attribute)
    so Tailwind's `display: flex` doesn't shadow the browser's
    built-in `[hidden]` rule. `[scrollbar-gutter:stable]` on
    both scroll containers reserves the scrollbar gutter so
    the layout doesn't jog when content crosses the scroll
    threshold. Viewer wrapper's `p-3` + border + `bg-muted/20`
    dropped: the inner iframe's own border frames the document
    directly, no double-border. `SimilarDocuments` gained a
    `hideHeading?: boolean` prop so the accordion trigger
    isn't duplicated by the component's internal heading.
    Rail trimmed `22rem` → `20rem`.

- [ ] **F109 · Candidate extraction quality** — HR's current state:
  *no candidate has a name.* The extraction pipeline (F22 text
  extraction → F23 metadata extraction) technically writes a
  `name` field to `document.metadata_`, but in practice real
  resumes come out with `name=None`. `CandidateService.create_from
  _document` faithfully pulls `meta.get("name")`, so nulls in
  produce nulls out. The list row falls back to email, and when
  the email is also missing we render "Unnamed candidate." This is
  the single most visible data-quality gap in the product. F109 is
  the overhaul pass to make candidate extraction production-ready.

  Scope covers the full pipeline — resume-specific name/email/
  phone parsing, skill-vocabulary grounding, LLM fallback for hard
  cases, a backfill script to fix every existing candidate, and
  evaluation so "production-ready" is measurable rather than a
  vibe.

  Libraries to flag per CLAUDE.md: `phonenumbers` (phone
  normalization, BSD), `email-validator` (already used for user
  emails, confirm reuse). Name parsing stays regex + LLM — no new
  NER dep.

  - [ ] **F109.a** Diagnose: write a one-off analysis script that
    walks every existing `documents` row of type `resume`, runs
    the current extractor, and reports the null-rate per field
    (name / email / phone / skills / experience_years / education).
    Save the numbers somewhere citable. Every later slice gets
    measured against this baseline — no guessing whether something
    "helped."
  - [ ] **F109.b** Deterministic name parsing v2. Resumes put the
    name in predictable places — first non-empty line of the first
    page, largest-font line in the first 20% of the PDF, the
    subject line of an emailed PDF, the filename stem ("John
    Doe - Senior Engineer.pdf"). Build a ranked extraction strategy
    that tries each source in order and returns the first
    high-confidence hit. Reject lines that look like headings
    ("CURRICULUM VITAE", "RESUME"), contact info, or all-caps
    locations. Target: <10% null-rate on the fixture corpus.
  - [ ] **F109.c** Email + phone hardening. Current `_first()`
    picks the first match; resumes often list personal + work
    email and the ordering isn't consistent. Rank candidates:
    prefer email that matches the name (`john.doe@` given
    `John Doe`), de-prefer company-sounding domains when there's
    a personal alternative. Phone via `phonenumbers` — parse,
    normalize to E.164, drop entries that don't validate. Multi-
    value support on the Candidate side (store all emails /
    phones, surface the primary in the UI) — minor schema change
    (`emails TEXT[]`, `phones TEXT[]` with a `primary_email`
    derived column).
  - [ ] **F109.d** Skill extraction grounding. Today skills come
    from F23 which regexes against a static list. Two upgrades:
    (1) Normalize aliases (`k8s ↔ kubernetes`, `js ↔ javascript`,
    `Sr.` removed from titles) before persistence — matches how
    F83 already tracks "skill normalization" in its backlog.
    (2) Extract from the *Skills* section when present (section-
    aware), not just a global regex sweep — massively reduces
    false positives ("leadership" from a project description).
  - [ ] **F109.e** LLM fallback for the hard cases. If deterministic
    extraction returns nulls on any of {name, email, phone,
    skills}, run a single structured-output LLM call against the
    resume's first 2 pages with a tight schema. Cost-bounded:
    only fires on misses, cached per document_id, timeout at 10s.
    Uses the existing provider abstraction from the RAG track — no
    direct OpenAI SDK import.
  - [ ] **F109.f** Backfill script:
    `scripts/reprocess_candidates.py` — walks every Candidate
    with a `source_document_id`, re-runs the v2 extractor against
    the stored text, updates the candidate row atomically, emits
    a per-candidate diff line (`before → after`). Supports
    `--dry-run`, `--owner <user_id>`, `--limit N`. Safe to rerun
    (extraction is idempotent; save overwrites with newer values
    but doesn't touch HR-entered overrides — F48.g territory).
  - [ ] **F109.g** Re-extraction on attachment add. When F46.b
    attaches a resume, trigger re-extraction so a freshly attached
    higher-quality resume gets priority over the older source.
    Same logic for "candidate's new resume replaces the old one"
    flow.
  - [ ] **F109.h** Eval harness: seed fixture of 30 real-ish
    resumes (anonymized, varied formats: single-column, two-
    column, scanned-OCR, LaTeX, Europass template, Google Docs
    export). Assert per-field accuracy ≥ target thresholds (name
    90%, email 95%, phone 85%, skills F1 ≥ 0.7). Runs in CI as a
    nightly — regression guard against future extraction changes.
  - [ ] **F109.i** Observability: log extraction decisions at
    INFO with a structured line (`extraction: doc=… method=line1
    fields=[name,email] fallback=false latency=230ms`) so the null-
    rate dashboard is just a query away. Pairs with F63's logging
    config work.
  - [ ] **F109.j** UI polish for edge cases. Candidate list's
    "Unnamed candidate" fallback becomes a subtle warning badge
    ("⚠ name not extracted — click to fix"), opening a small
    inline editor. Manual-override path exists today as a schema
    affordance (`name` is just a column) but nothing in the UI
    lets HR set it. Half-day job once the extractor is solid.

- [ ] **F110 · Reports & analytics** — distinct from F47's raw
  exports. Reports are **aggregated + narrative + periodic**
  artifacts for decision-makers (hiring managers, HR leadership,
  compliance). Exports answer "give me the data"; reports answer
  "what happened and what should I do." Ships after F47 (reuses
  the PDF rendering primitive) and F48.b/e (pulls from structured
  logs + application_events).

  Library: `matplotlib` (charts, permissive licence) — flagged
  per CLAUDE.md. No other new backend deps; chart rendering is
  server-side to a PNG embedded in the PDF so the frontend stays
  dumb.

  - [ ] **F110.a** Report primitive: `ReportService` composes
    (1) a data-fetch method (repo-backed, cached per report-id
    for 5 min), (2) a chart set (matplotlib PNGs written to
    MinIO `reports/<id>/<chart>.png`), and (3) a Jinja-rendered
    HTML template that F47.a's PDF primitive renders to bytes.
    HTML variant shipped too — for in-browser viewing before
    downloading. Reports route:
    `GET /reports/{type}?scope=<params>` returns HTML;
    `?format=pdf` swaps the output.
  - [ ] **F110.b** Per-job hiring-pipeline report (the most asked-
    for one). Sections: requisition header (job title, owner,
    status, days open), applicant pool (count, source
    breakdown: manual / gmail / import, top 5 skills in pool),
    funnel chart (new → shortlisted → interviewed → hired /
    rejected with drop-off %), match-score distribution histogram,
    time-in-stage stats (median days from `new` to
    `shortlisted`, etc. — pulls from F48.e
    `application_events`), and a "Next actions" block flagging
    candidates sitting in `new` >7 days.
  - [ ] **F110.c** Candidate one-pager (richer than F47.g.6). A
    narrative PDF for interview panels: header (name, role
    applying for, match score + breakdown sentence), skill
    coverage radar chart against job requirements, experience
    timeline, resume excerpts highlighting matched passages,
    and a "questions to explore" block generated from the gap
    between job requirements and resume. Interview-kit quality.
  - [ ] **F110.d** "Why this match" report. One-per-application:
    explanation paragraph (pairs with F45.e's explainability
    API), per-signal breakdown with mini-bars, matched skills
    with evidence snippets, experience-fit sentence, vector-
    similarity paragraph with the top 3 most-similar resume
    chunks. Shareable with hiring managers who don't trust "the
    algorithm" without seeing the reasoning.
  - [ ] **F110.e** Weekly / monthly HR activity report. Recruiter
    throughput: docs processed, candidates created, applications
    status-changed, jobs opened + closed, SLA compliance (avg
    time-to-first-review per applicant). Sent via F52 email
    (when it lands) as a scheduled Celery beat. Opt-in per user
    in F61 settings.
  - [ ] **F110.f** Diversity + fairness report. Reads from F48.f's
    fairness monitoring — distribution of shortlist / reject
    rates across the demographic-adjacent signals F48.f already
    logs. Legal / compliance lens, not an algorithm change.
    Admin-only; distribution surface, not per-candidate.
  - [ ] **F110.g** Audit / compliance report. Pulls from F48.e's
    `application_events`: every status change with actor, source,
    timestamp, reason. Filterable by date range, job, actor.
    Needed for SOC2 / GDPR right-to-audit requests. Bulk export
    to PDF + XLSX via F47 primitives.
  - [ ] **F110.h** Cross-job performance report. One per HR user
    or admin: all their jobs with fill rate, avg days open,
    source-of-hire breakdown (which doc-import channel produced
    the eventual hire), avg match score of hired candidates,
    bottleneck-stage flag (which status holds candidates
    longest). Identifies operational inefficiencies.
  - [ ] **F110.i** Search + RAG usage report. Pulls from the
    existing RAG observability (F81.b/c logs): query patterns,
    zero-result rate, most-surfaced docs, avg answer latency,
    feedback signal aggregation (F92's thumbs up/down when
    shipped). Feeds retrieval tuning decisions.
  - [ ] **F110.j** Gmail sync health report. Pulls from F51's
    sync worker logs: messages processed per account, extraction
    success rate, candidates created vs skipped, error summary.
    Surfaces stuck syncs before HR notices candidates stopped
    appearing.
  - [ ] **F110.k** Quarterly executive summary. Leadership roll-up:
    hires made, time-to-fill trend, applicant volume trend, top-
    filled roles, open reqs aging >30 days. Scheduled monthly +
    on-demand. The kind of report a VP of HR shows in the board
    meeting.
  - [ ] **F110.l** Match-score calibration report. Periodic
    algorithm-health check: score distributions over the last
    30 days, drift vs prior period, correlation between score
    and status transitions (are high-score candidates being
    shortlisted at higher rates? if not, the algorithm is
    mis-calibrated). Pairs with F45 tuning + F48.b observability.
  - [ ] **F110.m** Tests: snapshot tests per report template
    (HTML + PDF round-trip), chart rendering sanity (matplotlib
    determinism via `numpy.random.seed`), scope enforcement
    (HR can't pull cross-owner reports; admin can), cache
    invalidation on underlying data change.

---

## Phase 10 — Collaboration, platform & production readiness

Features that take Hireflow from "works for one HR user" to
"sellable to a real HR team on their own infra." Ordered roughly
by customer-blocker weight; F111 + F114 + F119 + F121 are the
can't-ship-without set.

- [ ] **F111 · Team collaboration (multi-user workspaces)** —
  today `Job.owner_id` and `Candidate.owner_id` make everything
  single-owner, so "our HR team of three shares this requisition"
  is impossible. Introduces workspaces (teams) as the primary
  tenancy unit; users join via invite; jobs and candidates are
  workspace-scoped with per-member roles.

  - [ ] **F111.a** Data model: `workspaces` (id, name, plan,
    created_at), `workspace_members` (workspace_id, user_id, role
    ∈ `owner / admin / member / viewer`, invited_at, joined_at).
    Migrate existing users into a personal workspace each.
    `Job`, `Candidate`, `Document` gain `workspace_id` (backfill
    from `owner_id → user.personal_workspace_id`).
  - [ ] **F111.b** Authorization shift: replace `owner_id ==
    actor.id` checks with workspace-membership + role checks.
    `UserRole.ADMIN` remains global-admin (support); workspace
    owner is the per-tenant admin. Owner-scope regression tests
    get parameterized on a team fixture.
  - [ ] **F111.c** Invite flow: `POST /workspaces/{id}/invites`
    generates a signed token emailed to the invitee (F52 reuse
    when it lands; stub email-to-console until then). Accept +
    join flow in the frontend under `/invite/:token`.
  - [ ] **F111.d** Workspace switcher UI: top-left sidebar header
    gains a workspace dropdown (matches Linear / Notion pattern);
    last-active workspace persists per user.
  - [ ] **F111.e** Member management page under `/settings/team`
    — list members, change role, remove member. Removing a member
    reassigns their artifacts to the workspace owner (prevents
    orphaned jobs — the ownership-transfer story from P2).
  - [ ] **F111.f** Per-workspace audit trail for membership
    changes (invite sent / accepted / role changed / removed);
    feeds F48.e's audit primitive.
  - [ ] **F111.g** Tests: cross-workspace access attempts (must
    404 / 403 before any data read), role-gate tests (viewer
    can't edit, member can't delete workspace).

- [ ] **F112 · Interview feedback, scorecards & notes** — pipeline
  has an `interviewed` status but nothing *inside* the interview
  step: no interviewer assignment, no structured feedback, no
  notes. Shortlisting without an interview loop ships half the
  story. Bundles P0 items #2 (interviews) and #3 (notes) since
  they share the same `application_notes` / `interview_*`
  schemas.

  - [ ] **F112.a** Notes primitive: `application_notes`
    (application_id, author_id, body TEXT, created_at,
    updated_at, visibility ∈ `workspace / interviewers`). HR can
    attach freeform notes to any application. Rich-text-lite
    (markdown) body.
  - [ ] **F112.b** Notes UI: thread pinned to the candidate
    drawer + detail page; author badge, relative timestamps,
    edit/delete author-only. Notifications fire to workspace on
    @mention (when F117 lands).
  - [ ] **F112.c** Interview schema: `interviews`
    (id, application_id, stage_name, scheduled_at, duration_min,
    status ∈ `scheduled / completed / cancelled / no_show`),
    `interview_panelists` (interview_id, user_id,
    feedback_status).
  - [ ] **F112.d** Scorecard templates: `scorecard_templates`
    (workspace_id, name, questions JSONB) — each question is
    `{id, prompt, rubric, scale, required}`. Admin creates
    templates per workspace; interview references a template id.
  - [ ] **F112.e** Feedback capture:
    `interview_feedback` (interview_id, panelist_id, template_id,
    answers JSONB, overall_rating INT, recommendation ∈
    `strong_hire / hire / no_hire / strong_no_hire`, submitted_at).
    Submitted-once; edit window 24h. Panelist can't see others'
    feedback until they submit theirs (blind mode, Lever-style).
  - [ ] **F112.f** Panel aggregation view: per-application "All
    feedback" panel shows overall recommendation distribution +
    per-question median + raw-answers. Hiring-manager decides
    based on panel synthesis; no AI auto-recommendation in v1.
  - [ ] **F112.g** Tests: blind-feedback enforcement, scorecard
    template CRUD, aggregation math, notes authorization.

- [ ] **F113 · Candidate-facing portal & public job board** —
  today everything is HR-uploaded or Gmail-synced; no way for an
  external person to submit an application. This unlocks inbound
  via "share this job link" which is the default expectation.

  - [ ] **F113.a** Public job board route: unauthenticated
    `GET /public/jobs/{slug}` renders a branded job page
    (workspace logo, job title, description, location,
    requirements, apply button). Only `open`-status jobs are
    public; 404 otherwise. `jobs.slug` column added (unique
    per-workspace, generated from title).
  - [ ] **F113.b** Apply flow: `/apply/{slug}` form — name,
    email, phone, resume upload (multi-file via F46), cover
    letter textarea, `consent_granted BOOLEAN` checkbox
    (required, feeds F123). No account creation in v1.
  - [ ] **F113.c** Submission endpoint:
    `POST /public/jobs/{slug}/apply` — rate-limited (F118),
    spam-filtered (honeypot field + simple heuristics), creates
    Candidate + Application atomically with
    `application_source='public_portal'`.
  - [ ] **F113.d** Confirmation UX: thank-you page with status
    link (opaque token), email receipt with same link. Candidate
    can check "still under review / shortlisted / not a fit"
    (never exposes internal status granularity — maps the 5
    internal statuses to 3 external labels).
  - [ ] **F113.e** Workspace setup: `/settings/branding` —
    workspace name, logo, primary color, careers page subdomain
    or path (`/careers/acme`). Applies to both portal + emails.
  - [ ] **F113.f** Anti-abuse: IP + fingerprint dedup,
    honeypot, CAPTCHA on 3+ submissions from same IP in an
    hour (hCaptcha — privacy-friendly default). Spam quarantine
    queue in HR review.
  - [ ] **F113.g** Tests: unauth access to draft/closed job
    404s, apply form validation, dedup on same email+job,
    CAPTCHA path, rate-limit enforcement.

- [ ] **F114 · Custom pipeline stages** — `ApplicationStatus`
  enum is hardcoded (`new / shortlisted / interviewed / hired /
  rejected`). Real orgs want `applied / phone_screen /
  tech_interview / onsite / offer / hired / rejected`. Or
  lighter. Flexibility gated on v1's rigid enum.

  - [ ] **F114.a** Schema: `pipeline_stages` (workspace_id,
    position, key, label, category ∈ `active / positive_terminal
    / negative_terminal`, created_at); `applications.status`
    becomes a FK to `pipeline_stages.id` (not enum). Every
    workspace starts with a default pipeline matching today's
    5-stage enum.
  - [ ] **F114.b** Stage editor UI under `/settings/pipeline` —
    drag-reorder list, rename, add, soft-delete (can't delete a
    stage with active applications; must reassign first).
  - [ ] **F114.c** Migration safety: existing `status` values
    map 1:1 to seeded default stages; backfill is idempotent.
  - [ ] **F114.d** Kanban + list updates: F93 columns become
    dynamic (read from pipeline_stages); column count is no
    longer 5. Overflow scroll handles many columns. F44.d's
    status multi-select becomes multi-stage.
  - [ ] **F114.e** Cross-workspace reports: F110.b (per-job
    pipeline report) reads stage config per job instead of the
    old enum. Score distributions stay comparable across
    workspaces via the `category` field.
  - [ ] **F114.f** Tests: reassign-before-delete enforcement,
    per-workspace isolation (deleting stage in workspace A
    doesn't affect B), dynamic-column rendering.

- [ ] **F115 · Candidate deduplication & merge** — F90.h added a
  per-owner unique `(owner_id, email)` constraint, so clear
  dupes can't be created via the same owner. Real dupes still
  slip through: candidate applies with different emails, same
  person with two resumes, cross-workspace (post-F111)
  collisions.

  - [ ] **F115.a** Match heuristics service: given a new
    candidate, return a list of probable duplicates within the
    workspace with a confidence score. Signals: normalized
    email, phone, name+DOB-adjacent fuzzy match (if DOB ever
    lands), resume text similarity (vector query over
    ChromaDB, cosine > 0.85 flags).
  - [ ] **F115.b** Duplicate review queue: `/candidates/
    duplicates` shows pairs above threshold, side-by-side diff,
    "Merge" / "Not a duplicate" actions.
  - [ ] **F115.c** Merge transaction: canonicalize on one
    candidate record, reassign all Applications +
    candidate_attachments + notes + interviews to the
    canonical id, soft-delete the duplicate. All-or-nothing in
    a single SQL transaction.
  - [ ] **F115.d** Ingest-time warning: when F46 / F113 create
    a candidate, surface a "Possible duplicate of X" banner
    before commit (not a block; HR may know it's distinct).
  - [ ] **F115.e** Tests: merge preserves all FK children,
    vector-similarity threshold tuning, not-a-duplicate
    persistence (once dismissed, don't re-surface the pair).

- [ ] **F116 · AI-generated-resume detection** — 2026 reality:
  GPT-authored resumes are common. HR wants a confidence label
  to weight judgment accordingly. Not a block (AI-assisted ≠
  fraudulent), a signal.

  - [ ] **F116.a** Detection service: per-document `ai_content_
    confidence FLOAT` on Document (0–1; 1.0 = almost certainly
    AI-generated). Run at F22 extraction time.
  - [ ] **F116.b** Model choice: start with a local detector
    (perplexity + burstiness heuristics via sentence-level
    tokens — no external API call). Evaluate against a seeded
    fixture of known-AI vs known-human resumes; target F1 ≥ 0.75.
    Upgrade path: fine-tuned small classifier if heuristics
    plateau.
  - [ ] **F116.c** UI surface: confidence badge on candidate
    row + drawer ("AI-assisted: likely / possibly / unlikely").
    Tooltip explains the signal is advisory. Filter in F44.d's
    filter bar: "Hide likely-AI" toggle.
  - [ ] **F116.d** Scoring interaction: does NOT auto-penalize.
    Signal surfaces, HR decides. F45.a eval fixture gains an
    AI-resume subset to confirm it doesn't quietly bias scoring.
  - [ ] **F116.e** Tests: deterministic signal on fixture,
    confidence round-trip, threshold calibration script.

- [ ] **F117 · In-app notifications & email digests** — no
  real-time "new candidate applied" alert, no "3 candidates
  awaiting review" digest. F110.e sketches weekly reports;
  F117 is the event-driven notification layer.

  - [ ] **F117.a** Event bus + schema: `notifications` (user_id,
    event_type, payload JSONB, read_at, created_at). Events:
    `application.created`, `application.status_changed`,
    `note.mentioned`, `interview.scheduled`, `job.status_changed`.
  - [ ] **F117.b** Delivery: in-app bell icon in top nav with
    unread count; dropdown lists recent; "Mark all read." Real-
    time via SSE (cheaper than WebSockets for one-way fanout).
  - [ ] **F117.c** Per-user preferences under `/settings/
    notifications` — granular toggles: "email me when X, bell
    me when Y, digest me for Z." Defaults sensible (mentions +
    new applications: bell + email; status changes: bell only).
  - [ ] **F117.d** Email digest: Celery beat aggregates
    unread + digest-preferred events, sends daily or weekly per
    user preference (reuses F52's email infra).
  - [ ] **F117.e** Throttling: coalesce bursts — if 10
    applications arrive in 1 minute, one notification "10 new
    applications" instead of 10 separate ones.
  - [ ] **F117.f** Tests: event emission coverage, SSE
    reconnection, preference enforcement, coalesce window.

- [ ] **F118 · Rate limiting** — no per-user / per-IP throttling
  on any endpoint today. Public portal (F113) + API (F122) need
  it as a ship condition; internal endpoints benefit from it too.

  - [ ] **F118.a** Redis-backed token-bucket middleware
    (`slowapi` — flag per CLAUDE.md, tiny dep). Per-IP for
    unauthenticated; per-user-id for authenticated.
  - [ ] **F118.b** Tiered limits: public portal strict
    (5 applications / hour / IP), auth'd normal (300 req / min
    / user), admin generous (1k / min), LLM endpoints separate
    (per-user token budget, not req count).
  - [ ] **F118.c** 429 response with `Retry-After` header +
    structured error body. Frontend shows a toast.
  - [ ] **F118.d** Admin override: per-workspace / per-user
    rate-limit bypass for trusted integrations (populates F122).
  - [ ] **F118.e** Tests: bucket exhaustion + recovery, header
    correctness, Redis-down fallback (fail-open, log warning —
    better than locking everyone out).

- [ ] **F119 · Self-hosted error tracking** — F70 mentioned a
  Sentry hook as optional and it never shipped, so there's no
  error aggregation in prod. Constraint: on-premise, privacy-
  focused — no SaaS Sentry. Recommendation: **GlitchTip** (open-
  source, Sentry-API-compatible so we reuse the Sentry SDK,
  lightweight single-container deploy, self-hostable on the
  same docker-compose network). Alternative: self-hosted Sentry
  (bigger footprint) or structured-logs-to-Loki (simpler but no
  stack-trace grouping).

  - [ ] **F119.a** Deploy GlitchTip via docker-compose.prod.yml
    (single Django container + shared Postgres + Redis we
    already run). Ops runbook in `docs/ops/glitchtip.md`.
  - [ ] **F119.b** Wire `sentry-sdk` into `app/main.py` (flagged
    dep) pointing at local GlitchTip DSN. Release tag from
    `GIT_SHA` env var so sourcemaps line up.
  - [ ] **F119.c** Frontend side: `@sentry/react` pointed at the
    same DSN for unhandled-promise + React-error-boundary
    capture. Strip PII at SDK level (`beforeSend` scrubs email /
    name / resume-text fragments).
  - [ ] **F119.d** Privacy controls: no source data leaves the
    box. `send_default_pii=False`, custom scrubber for resume
    text, IP anonymization on. Documented in
    `docs/privacy-posture.md`.
  - [ ] **F119.e** Alert routing: GlitchTip webhooks → local
    Slack bot / email on unseen-error-type or rate-spike.
  - [ ] **F119.f** Tests: forced exception reaches the local
    GlitchTip (smoke test in CI), PII scrubber catches email /
    resume fragments.

- [ ] **F120 · Data retention & cleanup** — Documents never
  expire. MinIO fills forever. No per-workspace retention
  policy. Both cost risk (unbounded storage) and compliance
  risk (GDPR data minimization).

  - [ ] **F120.a** Retention policy model: `retention_policies`
    (workspace_id, scope ∈ `documents / candidates /
    applications / activity_log`, action ∈ `delete / archive`,
    age_days INT, legal_hold BOOLEAN).
  - [ ] **F120.b** Nightly Celery beat job:
    `scripts/apply_retention.py` — walks eligible rows, soft-
    deletes past age_days (except legal_hold=true). Emits a
    summary log line per workspace.
  - [ ] **F120.c** Settings UI under
    `/settings/data/retention` — per-scope dropdown with
    presets (30d / 180d / 1y / 2y / 5y / forever) + legal-hold
    override toggle.
  - [ ] **F120.d** Soft-delete → hard-delete purge job (30d
    buffer after soft-delete for accidental recovery). MinIO
    blob deletion in the purge pass.
  - [ ] **F120.e** Per-workspace storage dashboard: current
    usage by document type + candidate count, flags when
    approaching configured plan quota.
  - [ ] **F120.f** Tests: retention boundary (exactly at
    age_days), legal_hold exclusion, cascade on hard-delete
    matches F48.h's deletion cascade.

- [ ] **F121 · Healthcheck & migration safety** — no `/healthz`
  endpoint (load balancers can't verify liveness), no
  documented zero-downtime migration protocol. Both are ops-
  maturity table stakes.

  - [ ] **F121.a** `GET /healthz` — liveness (always 200 if
    process is up) and `GET /readyz` — readiness (DB, Redis,
    ChromaDB, MinIO all reachable). Returns structured JSON
    per-dependency so orchestrators can fail-open sensibly.
  - [ ] **F121.b** Frontend: static health.html behind the
    reverse proxy for CDN / LB probes (no React bundle load).
  - [ ] **F121.c** Zero-downtime migration runbook:
    `docs/ops/migrations.md` — "always additive first, backfill
    in a separate commit, drop columns only after two
    deploys," Alembic command recipes for the common shapes
    (add nullable column, add index CONCURRENTLY, rename via
    add+backfill+drop).
  - [ ] **F121.d** Connection-draining on SIGTERM in
    `app/main.py` — stop accepting new requests, finish in-flight
    (respect a configurable grace period), close DB pool. Makes
    rolling deploys safe.
  - [ ] **F121.e** Migration CI gate: block merge if an Alembic
    revision has DROP/RENAME without a corresponding guard comment
    (`# safe-drop: deployed in vX.Y+ for at least one release`).
  - [ ] **F121.f** Tests: smoke test against `/healthz` +
    `/readyz` (mocked deps down → 503 for readyz, 200 for healthz).

- [ ] **F122 · Webhooks & public API** — no way for a customer
  to pipe events into Slack, Zapier, their ATS, or their own
  dashboard. Ships after F117 (reuses the event taxonomy) and
  F118 (rate-limits protect the outbound path).

  - [ ] **F122.a** API key management: `api_keys` (workspace_id,
    name, prefix, hashed_key, scopes JSONB, last_used_at,
    revoked_at). Settings UI to create / rotate / revoke.
    Display once, hash at rest. Bearer-token auth header.
  - [ ] **F122.b** Public API surface: documented subset of
    existing routes behind `/api/v1/*` prefix with stable OpenAPI
    spec; `X-API-Version` header negotiation. Start narrow:
    candidates, applications, jobs read + status change.
  - [ ] **F122.c** Webhook subscriptions: `webhooks`
    (workspace_id, url, secret, events TEXT[], active BOOLEAN,
    last_success_at, consecutive_failures). HMAC-SHA256 signed
    payloads; retry with exponential backoff (5 tries over
    ~15 min), deactivate after 20 consecutive failures.
  - [ ] **F122.d** Delivery worker: Celery task per event; each
    subscription is an independent send (partial failure
    doesn't block peers).
  - [ ] **F122.e** Delivery-log UI under `/settings/
    integrations/webhooks/{id}/log` — last 100 attempts,
    replay-button on failures.
  - [ ] **F122.f** Tests: signature verification, replay path,
    failure escalation, scope enforcement on API keys.

- [ ] **F123 · GDPR consent at collection** — F48.h covers
  right-to-deletion; collection-time consent (retention period
  acknowledgement, purpose-of-processing disclosure) isn't
  captured anywhere. EU / California applicants are blocked
  without this.

  - [ ] **F123.a** Consent record: `candidate_consents`
    (candidate_id, consent_type ∈ `processing / marketing /
    third_party_share`, granted BOOLEAN, text_version,
    granted_at, ip, user_agent). Immutable; revocations are
    new rows, not updates.
  - [ ] **F123.b** Public-portal (F113) apply form checkboxes
    wired to this table. Required checkbox = `processing`;
    optional = `marketing`.
  - [ ] **F123.c** HR-created candidates: capture source
    (`application_source`) + require a "legal basis"
    justification field (legitimate interest / contract / etc.)
    stored on Application.
  - [ ] **F123.d** Candidate self-service portal (F113.d token
    link) includes "Revoke consent" action; revocation triggers
    F120 retention policy early.
  - [ ] **F123.e** Privacy-notice versioning:
    `privacy_notices` (version, body_md, effective_from). Every
    consent row references the version in effect at the moment.
  - [ ] **F123.f** Tests: consent required for public submit,
    revocation cascade into retention, immutability (attempts
    to UPDATE the row → 500 by design; unit-tested).

- [ ] **F124 · Referral tracking** — who referred this
  candidate? Attribution matters for internal referral programs
  and for source-of-hire reports.

  - [ ] **F124.a** Schema:
    `Application.referred_by_user_id UUID NULL`,
    `Application.referral_source TEXT NULL`,
    `Application.referral_note TEXT NULL`. Nullable — most
    candidates aren't referrals.
  - [ ] **F124.b** Referral link generator: signed URL a
    workspace member shares externally; landing on the apply
    page (F113) auto-attributes the submission. Token carries
    referrer_user_id + job_id.
  - [ ] **F124.c** Settings UI under `/settings/referrals` —
    workspace member sees their active referral links, per-job
    conversion count.
  - [ ] **F124.d** Reports hook: F110.h cross-job performance
    report gains a "source-of-hire by referrer" breakdown.
  - [ ] **F124.e** Tests: token integrity, cross-workspace
    refusal, conversion tracking.

---

## Out of scope for v1
- ERP integrations, video tutorials, print-friendly quick-start, mobile apps
- GPU-optimized local LLM deployment (provider abstraction covers it later)
- Gmail integration (Phase 5 — deferred, needs Google OAuth setup)
- SSO (SAML / Google / Microsoft) — JWT local auth covers v1; ship when
  enterprise deals require it
- Resume versioning per candidate (new resume overwrites silently;
  revisit when customers ask)
- Bulk operations beyond status (bulk delete / reassign / move between
  jobs) — one-at-a-time works for v1 scale
- Internationalization (i18n / RTL / non-English extraction) — English
  assumption is baked into F109 extraction; revisit for EU/LATAM
- Staging environment + documented CI/CD pipeline — landing as
  `docs/ops/deploy.md` when a second environment is needed
- Ownership transfer on user removal (partial coverage in F111.e; full
  "reassign all their artifacts to X" admin flow is bigger)
- Interview scheduling (Google Calendar / Outlook integration) — F112
  tracks interview records; scheduling is a whole OAuth + availability
  pipeline
- PII redaction before LLM calls — F119.d scrubs error-tracking; RAG
  prompt scrubbing is a separate hardening pass
- LLM cost monitoring per-user (token budgets, cost dashboards) —
  F118.b has a placeholder; full usage-accounting ships later
- Seed data / demo mode — F97 onboarding covers first-use; a full
  demo-data fixture is nice-to-have
- On-candidate data enrichment (GitHub / public LinkedIn scraping) —
  ethics + terms-of-service concerns
- Plagiarism / resume-authenticity cross-checking beyond F116
