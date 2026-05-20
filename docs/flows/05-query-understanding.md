# 05 · Query understanding

Two passes happen before the query hits retrieval: the heuristic
**query parser** (F89.a) extracts structured filters from natural
language, and (on the RAG side only) the **intent classifier**
(F81.g) picks the answer shape.

This doc covers both + the acronym / tech-token normalization that
sits alongside them.

---

## Purpose

Close the gap between "free text the user typed" and "what the
retrieval and answer layers actually want":

- **Filters** (years, skills, doctype, date range) extracted
  deterministically so pure-semantic queries stay pure-semantic and
  filter-heavy queries *intersect* with structured data. Stops the
  system from pretending to answer "5+ years Python" by semantic
  match alone.
- **Intent** routes a RAG question to the right answer format —
  `count` → number + bullets, `comparison` → markdown table,
  `yes_no` → "Yes/No" on its own line. No more "here's a 200-word
  essay when I asked for a count."
- **Normalization** (acronym expansion, tech-token preservation)
  keeps `k8s` / `C++` / `Node.js` from falling off the edge of
  Postgres' english analyzer.

---

## Flow — heuristic query parser

```
raw query
    │
    ▼
HeuristicQueryParser.parse (services/query_parser.py:104)
    │
    │  empty? → QueryIntent(filters=ParsedFilters())  ← noop
    │
    │  1. _extract_years         (ordered regex patterns)
    │        - "at least N years"                     explicit
    │        - "over N years"                          explicit
    │        - "more than N years"                     explicit
    │        - "N+ years"                              explicit
    │        - "N-M years"                             range
    │        - "N years of experience"                 semi-explicit
    │        - "N years"   (loose, last resort)        fallback
    │     if None:
    │       _extract_seniority  (vocab lookup)
    │        - "senior" → 5, "staff" → 8, etc. (longest-first)
    │
    │  2. _extract_skills        (vocab lookup, longest-first)
    │        - non-alphanumeric boundary check for c++/.net/node.js
    │        - overlapping spans resolved by longer-wins
    │
    │  3. _extract_document_type (vocab lookup)
    │        - "resume" / "CV" / "report" / "contract" / "letter"
    │
    │  4. _extract_dates
    │        - "last N day/week/month/year"
    │        - "last <unit>"   (count=1)
    │        - "since YYYY"
    │        - "after YYYY-MM-DD"
    │
    ▼
QueryIntent(
    raw_query,
    filters=ParsedFilters(
        skills, min_experience_years, document_type,
        date_from, date_to,
    ),
    matched_spans=(...)  # observability: (start, end, label)
)
```

Called from **both** `SearchService.search` and
`SearchService.retrieve_chunks`. The two differ in how the filters
get applied:

- `search` → **fill gaps** (user-provided filters win; parsed ones
  fill `None` slots). `skills` are only promoted to a SQL filter
  alongside a strong signal (years / seniority / doctype / dates);
  bare `"Python"` stays a semantic query term.
- `retrieve_chunks` (RAG) → **hard intersection** when
  `has_strong_filter` is true. A year threshold means "exclude
  anyone below it", not "nudge the ranker." Pure-semantic queries
  skip the SQL path entirely.

`has_strong_filter` is defined in `adapters/protocols.py:349` as
"years or seniority or doctype or dates" — skills alone are
ambiguous and don't qualify.

---

## Flow — acronym + tech-token normalization

```
raw query
    │
    ├── vector path: UNTOUCHED
    │     (embedders already handle semantic equivalence)
    │
    └── FTS path:
            │
            ▼
        normalize_tech_tokens      (query_expansion.py:102)
            C++ → cpp, Node.js → nodejs, .NET → dotnet, etc.
            mirror of the SQL function in migration 2347719a1bd8
            │
            ▼
        expand_acronyms            (query_expansion.py:60)
            k8s → kubernetes, js → javascript, ml → machine learning, …
            one-directional, conservative vocab
            quoted substrings preserved
            │
            ▼
        websearch_to_tsquery('english', ...)
```

24 acronyms; ambiguous ones (cv, tf) deliberately omitted.

---

## Flow — intent classifier (RAG only)

```
RAG question
    │
    ▼
EmbeddingIntentClassifier.classify (services/intent_classifier.py:82)
    │
    │  empty? → IntentResult("general", 0.0, None)
    │
    │  q = embedder.embed_query(question)     (~5ms CPU)
    │
    │  for each pre-embedded canonical:
    │    sim = cosine(q, canonical_vec)
    │    best_by_intent[intent] = max(current, sim)
    │
    │  rank = best_by_intent sorted desc
    │  best_intent, best_score = rank[0]
    │  runner_up                 = rank[1].intent if any
    │
    │  if best_score < 0.55:
    │    intent = "general"
    │    runner_up = best_intent    (for observability)
    │  else:
    │    intent = best_intent
    ▼
IntentResult(intent, confidence, runner_up)
```

Canonicals (`services/intent_canonicals.py`) are 5-10 paraphrases per
intent, frozen tuples. Embedded **once** at classifier construction
(app boot). Per-query cost = one `embed_query` + ~60 cosine comparisons
≈ negligible compared to the LLM call it precedes.

Intents + their format rules live in `services/rag_prompts.py`
(`FORMAT_RULES`). An import-time exhaustiveness guard ensures every
declared intent has a format rule.

Current accuracy (eval harness): **93.7%** overall across 63 labeled
queries, 100% on every specific intent. Misses are `general` queries
that cosine-match nearby intents over the 0.55 threshold.

---

## Configuration knobs

| Setting / constant | Default | Effect |
|---|---|---|
| `KNOWN_SKILLS` (vocab) | `services/query_parser_vocab.py` | Skills the parser recognizes. |
| `SENIORITY_THRESHOLDS` | `services/query_parser_vocab.py` | `{"junior": 0, "senior": 5, ...}`. |
| `DOCUMENT_TYPE_KEYWORDS` | `services/query_parser_vocab.py` | Words that map to `DocumentType`. |
| `EmbeddingIntentClassifier.threshold` | 0.55 | Below-threshold → `general`. |
| `CANONICALS` | `services/intent_canonicals.py` | Paraphrases per intent; data-only changes. |
| `_ACRONYMS` | `services/query_expansion.py` | Acronym → canonical expansion. |
| `_TECH_TOKEN_SUBSTITUTIONS` | `services/query_expansion.py` | Tech-token → safe-token pre-pass. **Must sync with SQL function.** |

---

## Known issues / pain points

### Query parser

1. **Skill vocab is finite.** The parser only extracts skills that
   appear in `KNOWN_SKILLS`. A query mentioning "LangChain" won't
   promote it to a filter today. Expanding the vocab is cheap but
   unbounded — at some point a taxonomy + LLM-tier parser is the
   right shape.
2. **No NER for candidate names.** F89.b scopes this — today
   "Alice's Kubernetes experience" searches semantically only;
   there's no `document_ids` scoping by candidate.
3. **Month duration is approximated at 30 days.** "Last 6 months"
   counts back 180 days, not calendar months. Not wrong for HR
   filtering; slightly wrong for audit queries.
4. **Upper-bound dates ("before March 2026") aren't supported.**
   Only lower-bound. Whole space of "docs uploaded before X" is
   not covered.
5. **Year-extraction uses first-match-wins across ordered regex.**
   A query like "10+ years, need 3 years of Python" would match
   `10+ years` and ignore the 3. Reasonable today; surprising
   for complex queries.
6. **Seniority values are conservative.** `senior=5`, `staff=8`.
   A company that calls 3yr devs "senior" would get filtered too
   aggressively. Configurable but no per-owner override.
7. **`has_strong_filter` semantics are opaque to users.** A query
   with "Python" alone preserves pure-semantic; adding "2026" as
   a date suddenly flips to SQL-intersection. Users don't see this,
   can't predict it.

### Intent classifier

8. **Flat 0.55 threshold.** Some intents (`count`, `yes_no`) cluster
   tightly around their canonicals; `general` / `summary` / `list`
   are fuzzier. Per-intent thresholds would reclaim the last few
   points of accuracy.
9. **No online learning / feedback.** Wrong classifications don't
   flow back into canonicals. Adding a thumbs-down on the chat
   answer (F92.6 scope) would gather the signal; nothing consumes
   it yet.
10. **Canonicals aren't exercised at unit-test granularity.** The
    eval harness runs end-to-end classification; we don't have a
    "each canonical should self-classify" smoke test.
11. **Embedder share means a model swap re-embeds canonicals at boot.**
    Fine functionally; adds ~500ms to boot time per 60 canonicals.

### Normalization

12. **Tech-token SQL / Python duplication.** Covered in
    `04-lexical-and-fuzzy-index.md` §Known issues — same drift risk
    applies here.
13. **Acronym expansion doesn't cascade.** `swe` → "software
    engineer", but "software engineer" doesn't further expand. Fine
    in the single-pass model; an attacker could craft a pathological
    loop, but we control the vocab so it's a non-issue.

---

## Improvement opportunities

### Short-term

- **Per-intent confidence thresholds** keyed in `CANONICALS` metadata
  or a sibling table. Tighten `general` at 0.58, loosen `summary` at
  0.50. Would likely lift eval to 95%+.
- **Upper-bound dates.** Add `"before YYYY"` / `"until YYYY-MM-DD"`
  patterns and wire `date_to`. Minor addition; unlocks a query class
  we can't answer today.
- **Matched-span echo** on `/search` responses (already on the
  parser, not surfaced on the wire). Frontend can render "Python ·
  5+ years" as pill chips. Nice-to-have UX, costs one field on
  `SearchResponse`.
- **Per-canonical self-classification smoke test.** Iterate
  `CANONICALS`, assert each example classifies back to its own
  intent. Catches accidental paraphrase pollution at test time.

### Medium-term

- **Candidate-name NER (F89.b)** — lookup against indexed candidate
  names → `document_ids` scoping. Heuristic first (capitalized
  tokens matched against names), LLM tier opt-in.
- **Skill canonicalization** shared with candidate matching (F83) —
  "JS → JavaScript", "k8s → Kubernetes". Today the acronym table and
  matching's skill-normalization are independent; a single
  taxonomy avoids drift.
- **LLM-tier parser fallback (F89.e)** on low-confidence heuristic
  parses. Same Protocol; slot behind the heuristic. Only pays LLM
  cost on ~5% of queries.
- **Conversation memory (F81.f)** feeds back into intent — "show me
  more like that" is `general` without history but a ranking
  continuation with it.

### Long-term

- **Intent-conditional retrieval.** `count` queries want high recall
  (return all matching docs, not top-5); `comparison` queries want
  at-most-K-entities spread. Different retrieval budgets per intent.
  Current pipeline is one-size-fits-all.
- **Active-learning loop** — thumbs-up/down in the UI surfaces into
  a labeled-query store; periodic re-training of canonicals or
  threshold tuning.
- **Full-on LLM query understanding** — structured output schema,
  single call replaces parser + classifier + normalization. Expensive
  and adds latency; only if heuristic approach plateaus on
  accuracy.

---

## Cross-references

- **Code**: `backend/app/services/query_parser.py`,
  `app/services/query_parser_vocab.py`,
  `app/services/intent_classifier.py`,
  `app/services/intent_canonicals.py`,
  `app/services/query_expansion.py`,
  `app/services/rag_prompts.py`.
- **Protocol**: `QueryParser`, `IntentClassifier`,
  `ParsedFilters`, `QueryIntent`, `IntentResult` in
  `adapters/protocols.py`.
- **Related flows**: `04-lexical-and-fuzzy-index.md`,
  `06-hybrid-search.md`, `08-rag-pipeline.md`.
- **Eval**: `tests/eval/test_intent_accuracy.py`,
  `tests/eval/test_query_parser_accuracy.py`,
  `tests/eval/intent_queries.json`,
  `tests/eval/query_parser_cases.json`.
- **Design**: `docs/features.md` F81.g, F88.b, F89.a.
