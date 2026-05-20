# 09 · Candidate ↔ job matching

`POST /jobs/{id}/match` — score every candidate the owner has
against a job, persist the scores on `applications`, return ranked
results.

---

## Purpose

Given a job's title, description, required + preferred skills, and
experience range, compute a composite score per candidate. Drive
the UI's sorted candidate list and the "shortlist / reject" flow.

---

## Flow

```
POST /jobs/{id}/match    (routes/jobs.py)
    │
    ▼
MatchingService.match_candidates_to_job (services/matching_service.py:41)
    │
    │  job = JobRepository.get(job_id)
    │  candidates = CandidateRepository.list_by_owner(owner, limit=500)
    │
    │  vector_scores = _get_vector_scores(job, candidates)   (:150)
    │     - ChromaVectorStore.query(
    │         query_text = f"{job.title} {job.description}",
    │         n_results  = 100,
    │       )
    │     - for each hit, map document_id → candidate via
    │       candidate.source_document_id
    │     - similarity = max(0.0, 1.0 - hit.distance)   (cosine distance→similarity)
    │     - keep the MAX similarity per candidate across chunks
    │
    │  for each candidate:
    │     score     = _compute_score(job, candidate, vector_scores)   (:94)
    │               = 0.45 * skill_overlap
    │               + 0.20 * experience_fit
    │               + 0.35 * vector_similarity
    │     breakdown = _breakdown(job, candidate, vector_scores)        (:178)
    │               = {skill_match, experience_fit, vector_similarity}
    │
    │     app = ApplicationRepository.get_for_job_and_candidate(job_id, candidate.id)
    │     if app is None:
    │         app = ApplicationRepository.create(
    │                   candidate_id, job_id, score,
    │                   match_breakdown=breakdown,        ← persisted JSONB column
    │               )
    │     else:
    │         app.score = score
    │         app.match_breakdown = breakdown
    │         app = ApplicationRepository.save(app)
    │
    │  sort(results, by score desc)
    ▼
list[{candidate, application, score, breakdown}]
```

There is **no `upsert` on `ApplicationRepository`**. The service does an
explicit `get_for_job_and_candidate` lookup, then `create` (new pair) or
`save` (existing row) — see `matching_service.py:66-79`. Both branches
write `match_breakdown`: on `create` it's a keyword arg, on `save` it's a
field assignment before commit.

---

## Score components

### Skill overlap (45%)

`_skill_overlap` (`matching_service.py:112`):

```
required_match  = |required ∩ candidate_skills| / |required|
preferred_match = |preferred ∩ candidate_skills| / |preferred|
skill_score     = 0.7 * required_match + 0.3 * preferred_match
```

- Case-folded set intersection (`s.lower() for s in ...`).
- Zero when `job.required_skills` is empty — no required skills
  means the skill dimension can't differentiate candidates.
- No synonym / canonicalization — `JS` and `JavaScript` are
  different skills here.

### Experience fit (20%)

`_experience_fit` (`matching_service.py:130`):

```
if candidate.experience_years is None:
    return 0.3                                      # neutral when unknown

if years in [min, max]:                              # in range
    return 1.0
if max is None and years >= min:                     # open-ended min
    return 1.0
if years < min:                                      # underqualified
    gap = min - years
    return max(0.0, 1.0 - gap * 0.2)                 # 20% decay per year
if years > max:                                      # overqualified
    gap = years - max
    return max(0.0, 1.0 - gap * 0.15)                # 15% decay per year
```

Underqualified penalized harder than overqualified (20% vs 15% per
year gap) — reflects typical hiring preference.

### Vector similarity (35%)

ChromaDB cosine query: `{job.title} {job.description}` against the
chunk index. For each vector hit whose `document_id` maps to a
candidate's `source_document_id`, convert cosine distance to
similarity via `1 - distance`, keep the per-candidate max.

### Stored breakdown

`_breakdown` (`matching_service.py:178`) returns the per-signal dict
`{skill_match, experience_fit, vector_similarity}` (each rounded to 3
decimals). It is **not just a return-value field** — the service
persists it on the `Application` via the `match_breakdown` JSONB column
(`models/candidate.py:142`), passed as `match_breakdown=breakdown` on
`create` and assigned on `save`. The match list endpoint hydrates
`MatchBreakdown` straight off this column with no recompute.

---

## Configuration

Weights are hardcoded constants in `matching_service.py`:

```python
_WEIGHT_SKILLS = 0.45
_WEIGHT_EXPERIENCE = 0.20
_WEIGHT_VECTOR = 0.35
```

`experience_fit` decay slopes (`0.2` / `0.15`) also hardcoded.

---

## Known issues / pain points

1. **Candidate-set size cap at 500.** `list_by_owner(limit=500)` —
   users with more candidates silently lose the tail. No paging.
2. **`_get_vector_scores` always fetches 100 Chroma hits.** With
   many candidates, several per-candidate chunks may not make the
   cut → candidate gets `0.0` vector similarity → scored at
   `0.45 * skill + 0.20 * exp`. Not wrong; subtly wrong for
   candidates with marginal chunks.
3. **Query text is `{job.title} {job.description}`.** For a
   long description that's fine; for short jobs ("Senior SWE")
   the vector signal is thin.
4. **`source_document_id → candidate` is an O(candidates*hits)
   nested loop.** Works for 500 × 100 = 50k comparisons; would
   hurt at 10k candidates. Swap to a `{doc_id: candidate}` dict
   for O(hits).
5. **No skill canonicalization.** `"JS"` doesn't match
   `"JavaScript"`. A candidate who listed "JS" and a job requiring
   "JavaScript" scores zero on skills despite being a match.
   Pairs with F83 + F89.d.
6. **No education / location / remote signals.** Scored in F83
   scope; not yet.
7. **Experience fit assumes candidate has `experience_years`.**
   The classifier fills this when possible; when not, we fall to a
   neutral 0.3. Neutral is *wrong* when required is 10+ years and
   candidate lists none — we shouldn't give them 0.2 * 0.3 = 0.06
   free points.
8. **No weighted required vs preferred rollup at the
   *individual skill* level.** "Python" as required and
   "FastAPI" as preferred weight differently at category level
   (0.7 vs 0.3) but within each bucket every skill counts equally.
   A senior-Python role wants Python weighted much higher than
   "AWS (preferred)".
9. **Vector similarity dominates when skills info is missing.** A
   resume with no classifier-extracted skills gets `skill_score=0`,
   `exp_score=0.3` (if no years either), and a ~0.5 vector score →
   ~0.28 total. Reasonable but obscures "we don't actually know
   what this candidate knows."
10. **Application records are created even when scoring zero.**
    Every eligible candidate ends up in `applications` — fine for
    ranking but clutters the table with noise for big candidate
    pools.
11. **Match explanation is a raw score breakdown.** No human-
    readable "why this score" sentence. F83 scope.
12. **Scoring function is not configurable per-job.** Startups
    weight skills differently than enterprises. No job-level
    override.
13. **No hiring feedback loop.** If users reject the top-scored
    candidate repeatedly, nothing adjusts weights.

---

## Improvement opportunities

### Short-term

- **Replace the nested loop** with a precomputed `{doc_id:
  candidate}` dict. Trivial perf + clarity win.
- **Surface explanation.** Alongside `breakdown` include a short
  sentence: "Matches required skills X, Y; ±N years vs range."
  Model via a small helper on the service.
- **Pagination on `list_by_owner`.** Mirror documents pagination.
- **Stop scoring candidates missing all skill info.** Mark them
  `"needs re-processing"` rather than giving 0.3 neutral fit.

### Medium-term

- **Skill canonicalization (F83 + F89.d).** Shared vocabulary
  between the parser, matching service, and rule-based
  classifier. A single canonical form ("javascript") with synonyms
  (`js`, `ecmascript`) resolved at write time.
- **Per-skill weight** within required / preferred. Jobs specify
  `required_skills: [{skill: "python", weight: 1.0}, ...]`.
  Needs schema change; worth it.
- **Education + location signals.** Ordinal education hierarchy
  (PhD > MSc > BSc > Diploma), boolean remote-ok match, city
  proximity. All scoped in F83.
- **Configurable weights.** Job-level override for
  `skill / experience / vector` multipliers. Admin-only.
- **Eval harness on matching.** Curated (job, candidate pool,
  expected top-3) examples → regression signal on weight
  changes.

### Long-term

- **Learning-to-rank from shortlist/reject data.** Each explicit
  shortlist or reject feeds a feature store; train a per-owner
  reranker that complements the heuristic score.
- **Resume parsing overhaul.** Today `skills` come from a regex.
  Layout-aware extraction (F82.d, already in place) could feed a
  section-aware LLM parser that produces a normalized skill tree,
  experience timeline, and education ladder.
- **Active job matching.** New resume ingested → run match
  against all open jobs automatically, flag top matches for the
  owner. Push notification / dashboard surfacing.

---

## Cross-references

- **Code**: `backend/app/services/matching_service.py`,
  `app/repositories/candidate.py`,
  `app/repositories/job.py`,
  `app/api/routes/jobs.py`.
- **Routes**: `POST /jobs/{job_id}/match` (`jobs.py:133`) and
  `GET /jobs/{job_id}/candidates/export` (`jobs.py:171-194`) — the CSV
  export also calls `match_candidates_to_job`, then runs the ranked
  results through `export_candidates_to_csv`.
- **Upstream**: `01-document-upload-and-processing.md` (auto-candidate),
  `03-embeddings-and-vector-store.md` (vector similarity).
- **Design**: `docs/features.md` F40–F43 (shipped), F83 (planned
  matching accuracy), `docs/architecture.md` §8 candidate matching
  block.
