# 08 · RAG Q&A pipeline

`POST /rag/query` (JSON) and `POST /rag/stream` (SSE) — the full
answer-generation path from question to streamed tokens.

---

## Purpose

Answer HR questions over the user's own documents with:

- **Correct retrieval** — owner-scoped, READY-only, hybrid (vector
  + FTS + reranker), gated by distance + token budget.
- **Intent-aware formatting** — count, comparison, yes/no, ranking,
  summary, list, etc. render differently.
- **Typed citations** — filename + section + page + snippet + offset
  spans, ready for clickable chips in the UI.
- **Confidence** — `high`/`medium`/`low` or null (null = sentinel
  path, no answer grounded).
- **Streaming** — SSE so tokens appear as the model generates,
  with typed error events for provider failures.

---

## Flow

```
POST /rag/query                           POST /rag/stream
    │                                         │
    ▼                                         ▼
RagService.query (JSON)            RagService.stream_query (SSE)
    │                                         │
    └──────────────┬──────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────────┐
│ RagService._build_context (services/rag_service.py:269)      │
│                                                              │
│ 1. retrieve_chunks (F81.k)  — via ChunkRetriever Protocol    │
│      SearchService.retrieve_chunks(actor, query,             │
│                                    document_ids, limit)      │
│      does the same vector + FTS + reranker pipeline as       │
│      /search, but emits chunk-level RetrievedChunks.         │
│                                                              │
│ 1b. retrieve_candidate_summaries (F104.a)                    │
│      candidate-summary lane, capped at                       │
│      settings.rag_max_candidate_hits (default 3).            │
│      skipped when document_ids is pinned.                    │
│                                                              │
│    if not chunks and not candidates → return None            │
│                                                              │
│ 2. _apply_context_gate (F81.b + F81.c)  — chunks only        │
│      - cutoff distance filter (F81.b — tightening knob)      │
│      - token-budget walk (F81.c — default 4000)              │
│      - oversize top chunk: kept with WARN                    │
│      if not kept and not candidates → return None            │
│                                                              │
│ 3. IntentClassifier.classify(question) (F81.g)               │
│      - single embed_query call                               │
│      - cosine vs 60 canonical vectors                        │
│      - threshold 0.55 → below = "general"                    │
│                                                              │
│ 4. build_system_prompt(intent) (services/rag_prompts.py:277) │
│      Layer 1 IDENTITY   (stable)                             │
│      Layer 2 EVIDENCE_RULES (6 numbered rules, stable)       │
│      Layer 3 FORMAT_RULES[intent]  (per-intent shape + cap)  │
│      Layer 4 FEW_SHOT[intent]      (comparison / ranking)    │
│                                                              │
│ 5. Assemble user prompt + citations                          │
│      candidate hits render FIRST via _CANDIDATE_TEMPLATE,    │
│      then document chunks via _CONTEXT_TEMPLATE.             │
│      user_prompt = "Context:\n{blocks}\n\nQuestion: {q}"     │
│      chunk citation[i] = {                                   │
│        document_id, filename, chunk_index,                   │
│        text = chunk.text[:500],                              │
│        match_spans = find_match_spans(snippet, terms),       │
│        section_heading, page_number,                         │
│      }                                                       │
│      candidate citation[i] = same shape but                  │
│        chunk_index = None, text = candidate summary,         │
│        section_heading / page_number = None.                 │
│                                                              │
│ 6. confidence: _compute_confidence(kept) when chunks         │
│      present; else top candidate distance vs the F81.e       │
│      bands.                                                  │
│                                                              │
│    observability:                                            │
│      rag context: K/N chunks kept, ~T tokens                 │
│         (cutoff=..., budget=...)                             │
│         | intent=... conf=... runner=...                     │
│         prompt=v5 system_prompt_chars=...                    │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ JSON (/rag/query)              │ SSE (/rag/stream)           │
│                                │                             │
│ if ctx is None:                │ if ctx is None:             │
│   return RagResult(            │   yield DeltaEvent(         │
│     answer="Not in the         │     "Not in the provided    │
│      provided documents.")     │      documents.")           │
│                                │   yield DoneEvent           │
│                                │   return                    │
│                                │                             │
│ answer = asyncio.to_thread(    │ yield CitationsEvent        │
│   llm.complete,                │                             │
│   ctx.system_prompt,           │ try:                        │
│   ctx.user_prompt)             │   async for chunk in        │
│                                │     llm.stream(...):        │
│                                │     yield DeltaEvent(chunk) │
│                                │ except LlmProviderError:    │
│                                │   yield ErrorEvent(code=…)  │
│                                │   return                    │
│                                │ except Exception:           │
│                                │   yield ErrorEvent(         │
│                                │     code="llm_error")       │
│                                │   return                    │
│                                │                             │
│ return RagResult(answer, …)    │ yield DoneEvent(            │
│                                │   model, query_time_ms,     │
│                                │   confidence, intent,       │
│                                │   intent_confidence)        │
└──────────────────────────────────────────────────────────────┘
```

---

## Retrieval — shared with `/search`

F81.k collapsed RAG's retrieval onto `SearchService`:

```python
retriever = SearchService(documents, vector_store, reranker, query_parser)
rag_service = RagService(retriever, llm, intent_classifier)
```

`ChunkRetriever.retrieve_chunks` is the abstraction RAG sees. It
respects `actor.role` (owner-scoping, admin bypass), runs the same
vector + FTS + trigram + reranker pipeline, and emits
`RetrievedChunk` (chunk-level, with distance + score + metadata +
filename hydrated).

Difference vs `/search`:

- **No SQL-metadata path by default.** Structured filters for RAG
  arrive via `document_ids` ("ask about these docs") — skill/date
  filters are a search-UI concern. F89.a changed this slightly:
  a *strong* parsed filter (years / doctype / dates) activates the
  SQL path and hard-filters the vector + lexical hits before
  merging. A pure-semantic query still skips SQL.
- **FTS boosts vector-retrieved chunks; it never fabricates
  chunks for FTS-only docs.** For a chunk to feed the LLM we need
  chunk text — an FTS match on filename alone doesn't give us that.
- **Each chunk carries its author.** F103.c — `retrieve_chunks`
  hydrates `authored_by_id` / `authored_by_name` per chunk so the
  prompt header can read `Authored by: NAME` and the evidence rules
  can anchor a single-candidate answer.

See `06-hybrid-search.md` for the retrieval mechanics; the RAG side
just consumes them.

### Candidate-summary lane (F104.a)

Alongside chunk retrieval, `_build_context` runs a second lane:
`retriever.retrieve_candidate_summaries(actor, query, limit=...)`.

- Queries a dedicated Chroma collection of one-line recruiter briefs
  (one per candidate), owner-scoped, distance-cut by
  `rag_candidate_max_distance` (falls back to `rag_context_max_distance`).
- Capped at `settings.rag_max_candidate_hits` (default 3) so a flood
  of weak summary matches can't crowd chunks out of the token budget.
- **Skipped when `document_ids` is pinned** — a doc-scoped question
  shouldn't surface other candidates.
- Candidate hits render *before* document chunks in the user prompt
  (via `_CANDIDATE_TEMPLATE`), giving the LLM the recruiter-shape
  anchor before detail chunks.
- Each hit emits one citation with `chunk_index = None`; the frontend
  renders it through the same filename + snippet path as chunk
  citations.
- The early return is now `if not chunks and not candidates` — a
  question with zero chunks but a strong candidate-summary hit still
  produces an answer.

---

## Context gate (F81.b + F81.c)

Two independent filters in `_apply_context_gate`
(`rag_service.py:455`), applied to the chunk lane only — candidate
summaries are gated by their own per-lane distance cutoff in
`retrieve_candidate_summaries` and capped by `rag_max_candidate_hits`:

- **F81.b distance cutoff** — optional tightening knob. When
  `rag_context_max_distance` is `None`, the retriever already
  filtered at the search-threshold level; no double-filter needed.
  An explicit float re-filters tighter — useful for "only answer on
  high-confidence retrieval."
- **F81.c token budget** — greedy walk in retrieval order. Stop
  when the next chunk would exceed
  `rag_context_token_budget` (4000). Oversize top chunk (larger
  than the whole budget alone) is kept with WARN so pathological
  chunking doesn't kill the answer.

If the gate empties everything *and* the candidate lane is also
empty, `_build_context` returns `None` and callers emit the sentinel
path. When only candidate summaries survive, confidence falls back to
the top candidate's distance against the F81.e bands.

### Token estimation

`_estimate_tokens` uses Anthropic's "4 chars per token" rule of
thumb (`rag_service.py:46`). Ceil-divide to over-count rather than
under-count — budget-safe. Good enough for internal budgeting;
never used for hard API-limit checks.

---

## Intent + prompt composition (F81.g)

Three layers, composed per intent
(`services/rag_prompts.py`):

```
IDENTITY            — "senior HR research assistant" voice
EVIDENCE_RULES      — 6 numbered rules (stable)
FORMAT_RULES[intent]— per-intent shape + word cap
FEW_SHOT[intent]    — comparison + ranking only
```

`EVIDENCE_RULES` (F103.e) is six numbered rules: (1) citations —
filename in brackets after each claim, one per claim; (2) indirect
evidence — describe partial / project-level evidence rather than
deflecting; (3) naming — anchor on the named candidate, never blend
attributions, special-case the `Candidate:` block; (4) specificity
and quantification — keep metrics / durations / org names verbatim;
(5) multi-document claims — fold corroborating sources into one
sentence, each part cited to its own file; (6) fallback — the
machine-detectable `Not in the provided documents.` sentinel.

`PROMPT_VERSION = "v5"` (`rag_prompts.py:33`) logged per query so
answer-quality telemetry correlates to prompt edits.

`_check_format_rules_exhaustive` at module load ensures every
`Intent` literal has a corresponding `FormatRule`. Adding a new
intent without a format trips an import-time error, not a runtime
mystery.

---

## Wire contracts

### `POST /rag/query`

```json
RagResponse {
  answer: str,
  citations: [SourceCitation, ...],
  model: "claude-haiku-4-5-20251001",
  query_time_ms: 3840,
  confidence: "high" | "medium" | "low" | null,
  intent: "count" | "comparison" | "ranking" | "yes_no" | "locate"
        | "summary" | "timeline" | "extract" | "skill_list" | "list"
        | "general",                       # 11-value Intent literal
  intent_confidence: 0.78
}
```

### `POST /rag/stream` — SSE event stream

```
event: citations
data: {"event":"citations","data":[SourceCitation, …]}

event: delta
data: {"event":"delta","data":"token text"}

…

event: done
data: {"event":"done","data": StreamDone}
```

Or on mid-stream failure:

```
event: error
data: {"event":"error","data": {"code": "llm_rate_limited",
                                "message": "…",
                                "details": {"retry_after_seconds": 10}}}
```

Frame format: `event: <name>\ndata: <json>\n\n`. Both the `event:`
header and the JSON discriminator carry the event type — consumers
switch on either. `_sse_frame` at `routes/rag.py:142` serializes.

---

## Error taxonomy (F81.i)

Adapters translate SDK exceptions into domain types:

| Domain | HTTP | Source SDK / errors |
|---|---|---|
| `LlmUnavailable` | 503 | `APIConnectionError`, `AuthenticationError`, `PermissionDeniedError`, `InternalServerError`, `httpx.ConnectError`, `httpx.HTTPStatusError (non-429)` |
| `LlmRateLimited` | 429 | `anthropic.RateLimitError`, `httpx.HTTPStatusError (429)` — carries `retry_after_seconds` in `details` |
| `LlmTimeout` | 504 | `APITimeoutError`, `httpx.TimeoutException` |

`RagService.stream_query` catches `LlmProviderError` and emits an
`ErrorEvent` with `code + message + details`. Unknown exceptions
fall to a generic `llm_error` with full server-side traceback
(never leaked to the client).

`RagService.query` lets domain exceptions propagate; the F70 error
handler serializes them into the standard `ErrorResponse` envelope.

---

## Configuration knobs

| Setting | Default | Effect |
|---|---|---|
| `rag_context_max_distance` | `None` | F81.b tightening knob (None = trust retriever). |
| `rag_candidate_max_distance` | `None` | F104.a per-lane cutoff for candidate summaries (None = falls back to `rag_context_max_distance`). |
| `rag_max_candidate_hits` | 3 | F104.a cap on candidate-summary hits stitched into the context. |
| `rag_context_token_budget` | 4000 | F81.c budget; headroom on Ollama 8k, trivial on Claude 200k. |
| `rag_confidence_high_max_distance` | 0.20 | F81.e "high" band. |
| `rag_confidence_medium_max_distance` | 0.30 | F81.e "medium" band. |
| `reranker_top_k` | 20 | Candidate pool handed to the reranker (shared with search). |
| `llm_provider` | `anthropic` | `anthropic` or `ollama`. |
| `llm_model` | `claude-haiku-4-5-20251001` | Provider-specific. |
| `embedding_model` | `BAAI/bge-small-en-v1.5` | Reused by the intent classifier. |

---

## Known issues / pain points

1. **Context gate walks retrieval order blindly.** If retrieval
   returns three chunks all from the same doc, the gate happily
   keeps all three; we never apply MMR / per-doc diversity. Harmful
   on broad questions ("what are each candidate's strengths") when
   one candidate's resume dominates the budget.
2. **`_estimate_tokens` is a 4 chars/token heuristic.** Safe for
   budgeting but every provider / language combination has its own
   true ratio. We occasionally pack slightly under budget; rare
   outliers over.
3. **Citation snippet is `chunk.text[:500]` — hard character cut.**
   Works because chunk text is already packed ~1200 chars, but
   sentence-aware trimming (cut at last sentence boundary ≤500)
   would be prettier.
4. **Intent classifier's flat 0.55 threshold** — same drift as
   discussed in `05-query-understanding.md`. A few genuinely
   `general` queries tip into the wrong bucket.
5. **Prompt version is a string constant.** Bumping `PROMPT_VERSION`
   (currently `"v5"`) is manual — easy to forget after an edit. A
   hash-of-prompt-contents or a CI check would be better.
6. **Oversize-single-chunk WARN is silent to the user.** The answer
   generates but the UI has no indication that the model saw
   truncated context. Confidence band partly fills this role but
   doesn't know about oversize.
7. **No partial-retry on stream errors.** Rate-limit mid-stream
   kills the whole answer; the UI shows error. Ideally we'd buffer
   what we have and retry once with a slight backoff before giving
   up.
8. **Non-streaming path runs `llm.complete` via `asyncio.to_thread`**
   even when the provider offers async methods. Fine today; if we
   ever add structured output + tool calls, the async path would
   want a direct call.
9. **Intent classifier re-embeds canonicals at every process start.**
   ~60 embeddings × ~5ms = ~300ms of boot time. Cache in Redis?
   Probably not worth the complexity; noted.
10. **Citations are order-of-retrieval, not order-of-use.** If the
    LLM only cites 2 of 5 chunks in its answer, all 5 still appear
    as source cards. Harmless but noisy.
11. **`rag/query` (sync) doesn't return the `intent` field** when
    the sentinel path fires (no context). Shape is consistent with
    `RagResponse`'s `intent` default of `"general"`, but operators
    expecting an intent even on no-hits get a misleading label.
12. **Conversation memory (F81.f) blocks on F96 persistent chats.**
    Today every question is standalone; "what about the other
    resume?" means nothing to the retriever.
13. **Document-scope filtering is post-hoc.** `retrieve_chunks`
    retrieves without `document_ids`, then filters the merged
    chunk list. Means N*3 retrieval even when the user scoped to
    one doc. F81.k followup.

---

## Improvement opportunities

### Short-term

- **Diversity in the context gate.** Per-doc cap in `_apply_context_gate`
  (e.g. max 2 chunks from any single doc). Simple tunable; fixes
  the "one candidate dominates the context" failure class.
- **Sentence-aware snippet cut.** Trim `chunk.text[:500]` to the
  last sentence boundary ≤ 500 so the citation card ends cleanly.
- **Stream-level retry on `LlmRateLimited`.** One-shot retry with
  `retry_after_seconds`-delay before giving up. UI stays on the
  loading state.
- **Intent telemetry.** Counter `rag.intent.<name>` per response.
  Graph per-intent latency and confidence.
- **`document_ids` pushdown** to `full_text_search` + the vector
  `where` clause. Requires widening `DocumentRepository` signatures
  (already scoped as F81.k followup). Cuts wasted retrieval on
  scoped queries.

### Medium-term

- **Conversation memory (F81.f).** Redis-backed last-N-pairs per
  session, injected into the user prompt before the current
  question. Blocked on F96 persistent conversations (DB + sidebar +
  URL routing).
- **Hybrid budget strategy.** Keep the greedy walk as the default
  but fall back to a "pick top-1 per doc then fill remaining by
  score" algorithm when retrieval returns multi-doc multi-chunk
  results.
- **Regenerate with variants (F92.5 frontend).** "Give me a shorter
  answer" / "be more technical" — reuses context, re-prompts with
  an adjusted format rule. Pairs with user-visible regenerate
  button.
- **Eval harness on end-to-end RAG.** Today we have P@5/R@5/MRR on
  retrieval + intent accuracy, not answer quality. A golden-
  answer fixture with semantic-similarity scoring of the generated
  answer would close the loop.
- **Per-intent retrieval limits.** `count` wants high recall; `yes_no`
  wants 2-3 sharp chunks. Adjust `max_chunks` via intent.

### Long-term

- **Tool-calling / structured-output RAG.** For `count`, `comparison`,
  `ranking` intents, emit structured data (JSON) and render the
  table/list on the frontend rather than asking the LLM to format
  markdown. Eliminates a class of format-following errors.
- **Multi-hop retrieval.** For a question that needs two pieces of
  info in different docs, do a first retrieval, let the LLM plan a
  second retrieval, run it, then answer. Needs streaming
  infrastructure + longer turnaround; big win on complex questions.
- **RAG trace store.** Every answer persists `{question, chunks,
  system_prompt, model, answer, intent, feedback}` in a log table.
  Offline eval / fine-tuning / prompt versioning gets trivially
  easy. Storage cost low; compliance story needs thought.

---

## Cross-references

- **Code**: `backend/app/services/rag_service.py`,
  `app/services/rag_prompts.py`,
  `app/services/intent_classifier.py`,
  `app/services/intent_canonicals.py`,
  `app/api/routes/rag.py`,
  `app/schemas/rag.py`,
  `app/adapters/llm/*`.
- **Protocols**: `ChunkRetriever`, `RetrievedChunk`,
  `LlmProvider`, `IntentClassifier` in `adapters/protocols.py`.
- **Tests**: `tests/test_rag_streaming.py`,
  `tests/test_chunk_retrieval.py`,
  `tests/test_rag_prompts.py`,
  `tests/test_intent_classifier.py`,
  `tests/test_llm_error_translation.py`,
  `tests/eval/test_intent_accuracy.py`.
- **Frontend**: `12-frontend-answer-rendering.md`.
- **Design**: `docs/rag-system.md` (canonical),
  `docs/rag-pipeline.md` §2,
  `docs/features.md` F81.*.
