# RAG System Architecture

Canonical architecture reference for Hireflow's retrieval-augmented
generation stack. Captures the current state after the F81
answer-quality track (a, b, c, d, e, g, h, i, j, k) landed on top of
the earlier F30-family retrieval work.

Companion docs:

- [`architecture.md`](architecture.md) — system-wide architecture (auth,
  storage, layers, composition root).
- [`rag-pipeline.md`](rag-pipeline.md) — low-level ingestion/indexing
  pipeline diagrams + re-index scripts. Still canonical for that
  specific slice; this document covers the broader RAG system.
- [`rag-architecture.md`](rag-architecture.md) — original design-intent
  doc; kept for the "why we chose these shapes" rationale.
- [`search-hardening.md`](search-hardening.md) — retrieval edge-case
  catalog + open issues backlog.

**Read this document when** you're touching RAG-adjacent code:
`RagService`, `SearchService.retrieve_chunks`, `IntentClassifier`,
`rag_prompts.py`, `/rag/*` routes, or the answer-rendering components
in `search.tsx`.

---

## 1. What the system does

HR users upload documents (resumes, job descriptions, case studies)
and ask natural-language questions about them. RAG's job is to:

1. **Retrieve** the most relevant chunks from the user's own corpus
   (owner-scoped, READY-only).
2. **Classify** the question's answer shape (count, comparison,
   yes/no, …).
3. **Compose** an intent-specific system prompt on top of a stable
   identity + evidence rules layer.
4. **Generate** an answer via the configured LLM provider, streaming
   tokens back to the browser.
5. **Emit** typed citations + confidence + intent on the wire so the
   frontend can render structured output with clickable source
   chips.

Everything above runs per-request; nothing is pre-computed except the
chunk embeddings (indexing is a separate, one-time-per-upload job).

---

## 2. High-level flow

```
                          User question (+ optional document_ids)
                                         │
                                         ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │                   POST /rag/stream  (SSE)                         │
   │                   POST /rag/query   (JSON)                        │
   │                                                                   │
   │                   RagService.{stream_query, query}                │
   └───────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
       ┌─────────────────────────────────────────────────────────┐
       │  _build_context(actor, question, document_ids, limit)   │
       │                                                          │
       │  1. retriever.retrieve_chunks(...)   ──► ChunkRetriever  │
       │     (implemented by SearchService; F81.k)                │
       │  2. context gate                                         │
       │     - F81.b distance cutoff (optional tightening knob)   │
       │     - F81.c token budget   (4-chars/token estimator)     │
       │  3. IntentClassifier.classify(question)   ──► F81.g      │
       │  4. build_system_prompt(intent)   ──► rag_prompts.py     │
       │  5. assemble user prompt + citations with metadata       │
       └───────────────────────────────┬──────────────────────────┘
                                       │
                                       ▼
           ┌──────────────────────────────────────────────────┐
           │  LLM call through LlmProvider                    │
           │  - query(): asyncio.to_thread(llm.complete)      │
           │  - stream_query(): async for token in llm.stream │
           │  Translated errors on both paths (F81.i):        │
           │    anthropic.* / httpx.*  →  LlmRateLimited,     │
           │    LlmTimeout, LlmUnavailable, or re-raise       │
           └───────────────────────┬──────────────────────────┘
                                   │
            ┌──────────────────────┼────────────────────────────┐
            ▼                      ▼                            ▼
       CitationsEvent          DeltaEvent × N               DoneEvent
       (F81.a, -h, -j)         (F81.a streaming)            (F81.a + e + g)
       source snippets         tokens                       model, timing,
       + section_heading                                    confidence,
       + page_number                                        intent, intent_conf
                                   │
                                   ▼ (OR on mid-stream failure)
                               ErrorEvent
                               (F81.i: typed code + details)
```

All six RAG-answer-quality features (F81.a/b/c/d/e/g/i/j) compose
inside `_build_context` + the streaming pipeline. F81.h/k land in
retrieval.

---

## 3. Retrieval — `ChunkRetriever`

### Protocol boundary

`ChunkRetriever` (in `app/adapters/protocols.py`) is the abstraction
RAG sees:

```python
@runtime_checkable
class ChunkRetriever(Protocol):
    async def retrieve_chunks(
        self,
        *,
        actor: Any,                   # User with .id, .role
        query: str,
        document_ids: list[UUID] | None,
        limit: int,
    ) -> list[RetrievedChunk]: ...
```

`RetrievedChunk` carries everything downstream needs: `document_id`,
`filename`, `chunk_index`, `text`, `distance`, `score`, `metadata`.
Filename is hydrated inside the retriever so RagService never needs
the `DocumentRepository`.

### Implementation — `SearchService.retrieve_chunks` (F81.k)

`SearchService` implements `ChunkRetriever` alongside its existing
doc-level `search()` method. Both share the underlying retrieval
primitives (vector + FTS + trigram fallback) but collapse results
differently:

- `search()` → doc-level output with highlights (used by `/search` UI).
- `retrieve_chunks()` → chunk-level output (used by `/rag/*`).

```
                    ChunkRetriever.retrieve_chunks(actor, query, document_ids, limit)
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
              vector search               lexical FTS              fuzzy fallback
              (Chroma,                    (Postgres                (pg_trgm word_
               owner + type               search_tsv,              similarity over
               filtered where)            websearch_to_             filename + body
                                          tsquery, F88.a/b/d)      when FTS = 0)
                    │                         │                         │
                    ▼                         ▼                         ▼
              F86.c orphan drop     F88.c trigram fallback      normalized query
              (chunks for                                       via expand_acronyms,
              deleted / non-                                    normalize_tech_tokens
              READY docs)                                       (F88.b / F88.d)
                    │                         │                         │
                    └─────────────────────────┴─────────────────────────┘
                                              │
                                              ▼
                          ┌──────────────────────────────────────────┐
                          │  _rrf_merge_chunks  (F81.k, weighted)    │
                          │                                          │
                          │  Vector hits:   chunk-level rank        │
                          │                 score += w_vector /     │
                          │                 (RRF_K + rank + 1)      │
                          │  Lexical hits: doc-level rank boosts   │
                          │                 all vector-retrieved    │
                          │                 chunks from that doc.   │
                          │                 NO phantom chunks —     │
                          │                 FTS can't fabricate     │
                          │                 chunks the LLM can't    │
                          │                 read.                   │
                          │                                          │
                          │  Output: chunks ranked best-first        │
                          └──────────────────────┬───────────────────┘
                                                 ▼
                          ┌──────────────────────────────────────────┐
                          │  document_ids post-filter (if set)       │
                          │  Hydrate filenames (get_many)            │
                          │  Drop non-READY docs (F86.b)             │
                          └──────────────────────┬───────────────────┘
                                                 ▼
                          ┌──────────────────────────────────────────┐
                          │  Cross-encoder rerank (F80.5)            │
                          │  chunks with (query, chunk.text) pairs   │
                          │  via RerankCandidate.metadata[chunk_idx] │
                          │  Fallback to RRF order on failure        │
                          └──────────────────────┬───────────────────┘
                                                 ▼
                                    list[RetrievedChunk]
                                    ranked best-first
```

### Key invariants

- **Owner scoping is pushed into retrieval, not applied post-hoc.**
  HR users get `owner_id=actor.id` in Chroma's `where` clause and
  the FTS SQL predicate. Admin users bypass. This closes the silent
  leak that pre-F81.k RAG had.
- **SQL metadata path is intentionally excluded from
  `retrieve_chunks`.** Structured filters for RAG arrive via
  `document_ids` ("ask about these docs"), not skill/date typeahead
  — those are a search-UI concern.
- **FTS boosts vector-retrieved chunks; it never fabricates chunks
  for FTS-only documents.** Reasoning: for a chunk to feed an LLM,
  we need actual chunk text. An FTS match on filename alone doesn't
  give us content to inject into the prompt.

### Retrieval-time feature stack

| Feature | Effect |
|---|---|
| F80 | Distance ceiling on vector hits; dropped max-score normalization |
| F80.5 | Cross-encoder reranker over top-K candidates |
| F85.a | `EmbeddingProvider` protocol; `bge-small-en-v1.5` default |
| F85.c | Weighted RRF — `w_lexical=2.0` default so filename matches carry |
| F85.d | Per-model distance threshold via `embedder.recommended_distance_threshold` |
| F86 | Owner scoping in every retrieval path |
| F86.b | Non-READY doc chunks filtered out |
| F86.c | Orphan vector hits (chunks for deleted docs) dropped before RRF |
| F87 | Weighted FTS tsvector (filename A / skills B / body C) |
| F88.a | `websearch_to_tsquery` — phrases, OR, negation; empty-query short-circuit |
| F88.b | Acronym expansion (k8s → kubernetes) in lexical query |
| F88.c | `pg_trgm` trigram fallback when FTS returns zero |
| F88.d | Tech-token preservation (C++, .NET, Node.js) in both index + query |
| F81.k | Chunk-level RRF for RAG; owner scoping; no SQL path |

---

## 4. Context gate — F81.b + F81.c

`RagService._apply_context_gate(chunks, cutoff, budget)` runs in
retrieval order, with two independent filters:

```
chunks (ranked best-first)
    │
    ▼
F81.b — distance cutoff (optional tightening knob)
    cutoff = settings.rag_context_max_distance
    if None → skip (retriever already filtered at search threshold)
    else    → drop chunks whose .distance > cutoff
    │
    ▼
F81.c — token budget
    budget = settings.rag_context_token_budget  (default 4000)
    walk in order, accumulate via _estimate_tokens (4 chars/token)
    stop once next chunk would exceed budget
    ONE EXCEPTION — top chunk > budget alone: keep it + WARN log
      (preserves answer capability on chunking pathologies)
    │
    ▼
kept chunks → prompt
```

If `kept` is empty after the gate, `_build_context` returns `None`
and callers fire the no-hits sentinel path — a synthetic
`DeltaEvent` with `"Not in the provided documents."` + `DoneEvent`.
Uniform wire contract for both "retrieval found nothing" and
"everything filtered out."

---

## 5. Intent classification — F81.g

### Why embedding-based

The intent space (count / comparison / ranking / yes_no / locate /
summary / timeline / extract / skill_list / list + `general`) needs
paraphrase resilience. A regex matching "how many" misses "count
of", "quantify", "total number of", and so on. Embedding similarity
over canonical examples handles paraphrases for free.

```
         query
           │
           ▼
    ┌──────────────────────────────────────────────────┐
    │  EmbeddingIntentClassifier.classify(query)       │
    │                                                  │
    │  empty/whitespace → short-circuit to "general"   │
    │                                                  │
    │  q = embedder.embed_query(query)                 │
    │                                                  │
    │  scores: {intent: max cosine vs canonicals}      │
    │  ranked = sort(scores desc)                      │
    │                                                  │
    │  best, runner_up = ranked[0], ranked[1]          │
    │  if best.score < threshold (0.55):               │
    │      intent = "general"                          │
    │      runner_up kept (observability)              │
    │  else:                                           │
    │      intent = best.intent                        │
    └───────────────────┬──────────────────────────────┘
                        ▼
              IntentResult(intent, confidence, runner_up)
```

### Canonicals as data

`backend/app/services/intent_canonicals.py` holds 5-10 paraphrases
per intent as frozen tuples. Adding a new intent or paraphrase is
data-only — no code change required.

```python
CANONICALS: dict[Intent, tuple[str, ...]] = {
    "count": (
        "how many candidates have Kubernetes experience",
        "count of resumes mentioning Python",
        "number of senior engineers in the corpus",
        # ... 4 more paraphrases
    ),
    "comparison": ( ... ),
    ...
    "general": (),  # the below-threshold fallback bucket
}
```

### Accuracy measurement

`backend/tests/eval/intent_queries.json` — 63 labeled queries
covering every intent. `make eval-intent` runs the real bge-small
classifier, prints a per-intent scorecard, and fails below
`INTENT_ACCURACY_THRESHOLD = 0.80`.

Current score: **93.7% overall**, every specific intent at 100%;
the misses are `general` queries that cosine-match nearby intents
above threshold. Per-intent threshold tuning is the open follow-up.

### Performance

- **Construction**: ~N canonicals × one embedding call each (~60 vecs).
  Happens once at startup.
- **Per query**: one `embed_query` call (~5ms on CPU) + ~60 cosine
  comparisons (O(N×d), negligible).
- **Zero marginal latency** on the request path relative to the LLM
  call it precedes.

---

## 6. Prompt composition — F81.d + F81.g

`backend/app/services/rag_prompts.py` composes the system prompt from
three layers + optional few-shots:

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1 — IDENTITY (stable)                            │
│  "You are a senior HR research assistant. You read      │
│  documents carefully and summarize them for a hiring    │
│  manager who is short on time…"                         │
│                                                         │
│  Defines voice + tone. One paragraph. Rarely changes.   │
├─────────────────────────────────────────────────────────┤
│  Layer 2 — EVIDENCE_RULES (stable)                      │
│  - Cite filename inline in square brackets per claim    │
│  - Exact fallback sentinel: "Not in the provided        │
│    documents." + natural next-step sentence             │
│  - Introduce people once with a short qualifier, then   │
│    use the short form                                   │
│                                                         │
│  Machine-detectable parts (sentinel, citation syntax)   │
│  live here so they're intent-agnostic.                  │
├─────────────────────────────────────────────────────────┤
│  Layer 3 — FORMAT_RULES[intent] (varies)                │
│                                                         │
│  count:       number alone → bullets;        cap 60 w   │
│  comparison:  markdown table + Source col;   (no cap)   │
│  ranking:     ordered list;                  cap 120 w  │
│  yes_no:      Yes/No + one sentence;         cap 40 w   │
│  locate:      bulleted doc list;             cap 80 w   │
│  summary:     name → salient fact → 2-3 s;   cap 150 w  │
│  timeline:    markdown table Year/Event;     (no cap)   │
│  extract:     bulleted items;                (no cap)   │
│  skill_list:  bullets grouped by doc;        (no cap)   │
│  list:        bulleted list;                 (no cap)   │
│  general:     (no extra format);             cap 200 w  │
├─────────────────────────────────────────────────────────┤
│  Layer 4 — FEW_SHOT[intent]                             │
│                                                         │
│  Only comparison + ranking today — the intents Claude   │
│  drifts on without a concrete exemplar. One Q/A pair    │
│  each. Lands at the end of the prompt (closest to the   │
│  model's output context).                               │
└─────────────────────────────────────────────────────────┘
```

`build_system_prompt(intent)` is a pure function. An import-time
exhaustiveness guard ensures every `Intent` literal has a
`FormatRule`, so adding a new intent without a format can't
ship silently.

`PROMPT_VERSION = "v2"` is logged per query for A/B correlation;
lets us tie answer-quality telemetry to prompt edits.

---

## 7. Answer generation — streaming + sync

### Wire contracts

Two endpoints consume the same `_build_context`:

| Endpoint | Response | When used |
|---|---|---|
| `POST /rag/stream` | `text/event-stream` (SSE); events `citations` → `delta` × N → `done` (or `error`) | Browser chat UI (F81.a) |
| `POST /rag/query` | JSON `RagResponse` | Tests, non-browser clients, eval |

Both return identical content shape — same citations, same intent,
same confidence. Streaming just delivers it progressively.

### LlmProvider — two methods

```python
class LlmProvider(Protocol):
    def complete(self, system: str, user: str) -> str: ...
    def stream(self, system: str, user: str) -> AsyncIterator[str]: ...
    @property
    def model_name(self) -> str: ...
```

`complete` is synchronous — used by Celery workers (classifiers,
contextualizers) via `asyncio.to_thread` from the async route.
`stream` is async-native to avoid thread-bridge workarounds; backed
by `AsyncAnthropic.messages.stream` (Claude) and
`httpx.AsyncClient.stream` (Ollama).

### SSE frame format

Each event is a Pydantic discriminated union instance serialized to
JSON, emitted as:

```
event: <name>\n
data: {"event": "<name>", "data": {...}}\n
\n
```

Named events (`event: ...`) let native `EventSource` register
listeners; the JSON payload carries the discriminator so a single
`fetch`-based `onmessage` handler can switch on it. Frontend uses
the latter because native `EventSource` is GET-only + cannot carry
`Authorization` headers.

### Error taxonomy — F81.i

Adapter-level translators (`_translate_anthropic_error`,
`_translate_httpx_error`, `_translate_urllib_error`) map SDK
exceptions onto domain types:

| Domain exception | HTTP status | Source SDK types |
|---|---|---|
| `LlmUnavailable` | 503 | `APIConnectionError`, `AuthenticationError`, `PermissionDeniedError`, `InternalServerError`, `httpx.ConnectError`, `httpx.HTTPStatusError (non-429)` |
| `LlmRateLimited` | 429 | `anthropic.RateLimitError`, `httpx.HTTPStatusError (429)` — carries `retry_after_seconds` when the provider sends the header |
| `LlmTimeout` | 504 | `APITimeoutError`, `httpx.TimeoutException` |

`RagService.stream_query` catches `LlmProviderError` (the base) and
emits `ErrorEvent(code=exc.code, message=str(exc), details=exc.details())`.
Unknown exceptions fall through to a generic `llm_error` with full
server-side traceback — the client never sees raw SDK strings.

`RagService.query` lets domain exceptions propagate; the existing
F70 error handler serializes them to the standard `ErrorResponse`
envelope with the right HTTP status.

---

## 8. Schemas on the wire

### `RagResponse` (sync)

```python
{
  "answer": "…",
  "citations": [SourceCitation, …],
  "model": "claude-3-haiku-20240307",
  "query_time_ms": 3840,
  "confidence": "high" | "medium" | "low" | null,   # F81.e
  "intent":     "count" | "comparison" | … | "general",  # F81.g
  "intent_confidence": 0.78,                         # F81.g
}
```

### `SourceCitation`

```python
{
  "document_id":      "…",
  "filename":         "alice_resume.pdf",
  "chunk_index":      3,
  "text":             "…up to 500-char snippet…",
  "match_spans":      [[0, 8], [45, 53]],   # F92.1 highlight offsets
  "section_heading":  "Experience" | null,  # F81.h (from F82.e metadata)
  "page_number":      2 | null,             # F81.h
}
```

### `StreamDone` (SSE `done` event payload)

Same fields as `RagResponse` minus `answer` + `citations` (those
travel in their own events). `intent` + `intent_confidence` fire
on every `done`, never null — frontend always has a value to
switch on.

---

## 9. Frontend integration

### Chat UX (`frontend/src/pages/search.tsx`)

- **Streaming consumer** (`src/api/rag-stream.ts`): ~100 lines of
  `fetch` + `ReadableStream` + manual SSE frame parsing. No library
  dependency. Sends `Authorization: Bearer <token>` header from the
  shared client.
- **Typing indicator** only fires while the assistant bubble has no
  content yet. Once the first `delta` lands, the bubble swaps to
  markdown rendering with a subtle blinking cursor while `streamingMessageId`
  is still set.
- **Layout**: Claude-style — page fills viewport; messages scroll
  inside a `ScrollArea`; input is pinned at the bottom of the card.

### Markdown rendering — F81.g

`react-markdown` + `remark-gfm` render assistant content so tables,
ordered/unordered lists, and strikethrough all display natively.

`AssistantMarkdown` provides component overrides on `p`, `li`, `td`,
`th`, `table`, `ul`, `ol`. A `renderWithCitations` wrapper walks
top-level string children, runs `parseSegments`, and replaces
matching `[filename.pdf]` markers with `<CitationMarker>` chips.
Result: citation chips render cleanly inside table cells, list
items, and prose — regardless of the answer's markdown shape.

### Citation chips — F81.j + F81.h

`parseSegments` regex-matches complete `[...]` spans against
`citations[].filename` (exact match, then lowercase fallback).
Unknown brackets render as plain text (no false-positive chips).
Streaming-safe — incomplete `[alice_` without a closing `]` stays
as text until the next delta arrives.

Hovering a chip shows a tooltip with filename + section heading +
snippet. Clicking scrolls the matching source card below into view
with a brief primary-colour ring flash.

### Confidence + intent — F81.e + F81.g

The `done` event feeds three fields into the assistant message:
`confidence` drives a coloured `Badge` next to the model/timing
metadata; `intent` is currently observability-only (available for
future styling, e.g. icon per intent).

---

## 10. Data model

```
Postgres
├── users                         id, email, role (admin | hr), …
│       ↓ (FK)
├── documents                     owner_id,
│                                 extracted_text,
│                                 search_tsv  (GENERATED tsvector, GIN)
│                                              setweight: filename A
│                                                         skills   B
│                                                         body     C
│                                 metadata    (jsonb: skills, experience_yrs, …)
│                                 status      (PENDING/PROCESSING/READY/FAILED)
│                                 extraction_version
│                                 chunking_version
│                                 embedding_model_version
│       ↓ (CASCADE)
├── document_elements             typed regions from F82.d
│                                 (Title, NarrativeText, Table, ListItem, …)
│                                 with page_number + order_index
│       ↓ (derived from, not FK)
└── activity_logs, candidates, …  (see architecture.md)

Chroma
└── collection "documents_<model_slug>"  (per-embedder naming)
    per-chunk metadata:
      document_id, owner_id,
      chunk_index, total_chunks, chunk_kind,
      section_heading, page_number, element_kinds,
      chunking_version
```

Version columns let us re-index subsets:
- `scripts/reextract_all.py` — rebuild elements + chunks from MinIO
  blobs (slow; after extraction strategy change)
- `scripts/reindex_embeddings.py` — rebuild Chroma vectors from
  persisted `document_elements` (fast; after embedder swap)

---

## 11. Observability

Per-query INFO log from `RagService._build_context` carries every
signal downstream consumers + ops need:

```
rag context: 5/5 chunks kept, ~1247 tokens (cutoff=none, budget=4000) |
intent=comparison conf=0.87 runner=ranking prompt=v2 system_prompt_chars=1892
```

Fields:

| Field | Signal |
|---|---|
| `kept/total chunks` | F81.b + F81.c gate effectiveness |
| `~tokens` | F81.c budget consumption |
| `cutoff=` | F81.b applied threshold (`none` if knob unset) |
| `budget=` | F81.c configured budget |
| `intent=` | F81.g classifier output |
| `conf=` | F81.g confidence |
| `runner=` | F81.g second-best intent (ambiguity signal) |
| `prompt=` | `PROMPT_VERSION` for A/B correlation |
| `system_prompt_chars=` | Guards against prompt bloat |

Today this log is emitted but not visible in dev runs because the
project has no root logger handler (`app.*` loggers drop without
one). F63 — a `DEBUG`-guarded `logging.basicConfig(level=INFO)` —
is the follow-up that makes these lines visible locally. Production
deployments configure logging externally.

Eval accuracy is visible via `make eval-intent` (prints per-intent
scorecard + misclassifications for triage).

---

## 12. Configuration knobs

All live in `backend/app/core/config.py`:

| Setting | Default | Effect |
|---|---|---|
| `embedding_provider` | `local` | Choose `EmbeddingProvider` impl |
| `embedding_model` | `BAAI/bge-small-en-v1.5` | Per-model Chroma collection + threshold table |
| `llm_provider` | `anthropic` | `claude` or `ollama` |
| `llm_model` | `claude-3-haiku-20240307` | Provider-specific model name |
| `reranker_provider` | `local` | `local` or `none` (disable) |
| `reranker_top_k` | 20 | Candidates handed to cross-encoder |
| `search_max_distance` | `None` | Override embedder's threshold (search path) |
| `rrf_weight_vector` | 1.0 | RRF weight on vector contributions |
| `rrf_weight_lexical` | 2.0 | F85.c — boosts filename-matching lexical hits |
| `rag_context_max_distance` | `None` | F81.b tighter cutoff (None = trust retriever) |
| `rag_context_token_budget` | 4000 | F81.c token budget for context |
| `rag_confidence_high_max_distance` | 0.20 | F81.e "high" band threshold |
| `rag_confidence_medium_max_distance` | 0.30 | F81.e "medium" band threshold |

None of these require a migration or restart beyond the normal
config reload.

---

## 13. Composition root

`backend/app/api/deps.py` constructs the graph once at import time:

```python
# Module-level singletons (stateless adapters + heavy models)
_vector_store       = ChromaVectorStore(..., embedder=get_embedding_provider(settings))
_llm_provider       = get_llm_provider(settings)      # Claude or Ollama
_reranker           = get_reranker(settings)          # local or Null
_intent_classifier  = EmbeddingIntentClassifier(_vector_store.embedder, CANONICALS)

def get_rag_service(documents: DocumentRepositoryDep) -> RagService | None:
    if _vector_store is None or _llm_provider is None or _intent_classifier is None:
        return None
    retriever = SearchService(documents, _vector_store, reranker=_reranker)
    return RagService(retriever, _llm_provider, _intent_classifier)
```

Each heavy resource (embedder model, reranker model, classifier
canonicals) loads exactly once per process. `SearchService` is
stateless apart from its injected deps, so constructing one per
request is free.

Construction failures (embedder dead, Chroma down, classifier init
error) log a WARNING and set the relevant singleton to `None` →
`get_rag_service` returns `None` → `/rag/*` route raises
`ServiceUnavailable` (503) with a clear envelope. No silent
degradation.

---

## 14. Failure modes + graceful degradation

| Failure | Observable signal | User-visible behavior |
|---|---|---|
| ChromaDB down at startup | WARN log; `_vector_store = None` | `/rag/*` → 503 with `llm_unavailable` |
| LLM provider not configured | `_llm_provider = None` | `/rag/*` → 503 |
| Classifier init fails | WARN log; `_intent_classifier = None` | `/rag/*` → 503 |
| All chunks filtered by F81.b cutoff | "rag context: 0/N chunks kept" INFO log | Sentinel "Not in the provided documents." + suggestion |
| Top chunk exceeds F81.c budget | WARN log; chunk kept anyway | Answer generated from one oversized chunk |
| LLM rate-limited mid-stream | WARN log; `LlmRateLimited` dispatched | `error` SSE event with `code="llm_rate_limited"` + `retry_after_seconds` in details |
| LLM timeout | `LlmTimeout` dispatched | `error` SSE event with `code="llm_timeout"` |
| Unknown LLM exception | `logger.exception` with full traceback | `error` SSE event with generic `code="llm_error"` — SDK internals never reach the client |
| Malformed `[bracket]` in answer not matching any citation | — | Rendered as plain text, not a chip |
| Incomplete marker mid-stream | — | Rendered as text until next delta arrives (streaming-safe regex) |

---

## 15. Feature → code map

| F81 slice | Primary touch points |
|---|---|
| F81.a streaming | `LlmProvider.stream`; `adapters/llm/claude.py`, `ollama.py`; `stream_query` in `rag_service.py`; `POST /rag/stream` route; `rag-stream.ts` consumer |
| F81.b distance cutoff | `rag_context_max_distance`; `_apply_context_gate` in `rag_service.py` |
| F81.c token budget | `rag_context_token_budget`; `_estimate_tokens`; `_apply_context_gate` |
| F81.d base prompt rules | Now lives as `IDENTITY` + `EVIDENCE_RULES` in `rag_prompts.py` |
| F81.e confidence | `_compute_confidence` in `rag_service.py`; `confidence` on schemas |
| F81.g intent + structured formats | `intent_canonicals.py`, `intent_classifier.py`, `rag_prompts.py`; `intent` + `intent_confidence` on schemas; frontend markdown renderer |
| F81.h source linking | `section_heading` + `page_number` on `SourceCitation`; source-card rendering + scroll handler |
| F81.i error taxonomy | `domain/exceptions.py` `LlmProviderError` + subclasses; adapter `_translate_*` helpers; MRO fallback in error handler |
| F81.j inline citation chips | `parseSegments` + `CitationMarker` in `search.tsx` |
| F81.k shared retrieval pipeline | `ChunkRetriever` Protocol + `RetrievedChunk` dataclass; `retrieve_chunks` + `_rrf_merge_chunks` in `search_service.py`; `RagService` constructor swap |

---

## 16. Open follow-ups

- **F81.f** conversation memory — blocked on F96 (persistent
  conversations). The prompt stack is ready to inject history once a
  store exists.
- **F63** dev-mode logging config — surfaces the per-query
  observability line locally without restarting with a custom config.
- **F81.h2 / F91** full in-app doc-preview modal at the cited
  section; today the sources panel gives "relevant section" via
  `section_heading` without opening the doc.
- **F92.11** frontend error-UX polish — countdown on
  `retry_after_seconds`, retry buttons on `llm_timeout`,
  ops-facing note on `llm_unavailable`.
- **Intent threshold tuning** — the flat `0.55` cosine threshold
  lets a few genuinely-`general` queries drift into nearby intents.
  Per-intent thresholds or a higher flat threshold would tighten
  the `general` bucket.
- **Phase 2 LLM-tier classifier fallback** — only if the eval
  plateaus below ~95%. The `IntentClassifier` Protocol is open for
  it.
- **`document_ids` pushdown to FTS/SQL** — today the retriever
  post-filters on this field. Pushdown would require
  `DocumentRepository.full_text_search` to accept a doc-id filter.

---

## 17. When to touch what

**Adding a new intent:**
1. Add 5-10 paraphrases to `CANONICALS` in `intent_canonicals.py`.
2. Add the literal to the `Intent` union.
3. Add a `FormatRule` entry in `FORMAT_RULES` (exhaustiveness guard
   will fail the build otherwise).
4. Optionally add few-shots for format-sensitive intents.
5. Add labeled queries to `intent_queries.json`.
6. Run `make eval-intent`; fix canonicals or threshold until
   passing.

**Swapping embedder model:**
1. Update `EMBEDDING_MODEL` in env.
2. `scripts/reindex_embeddings.py` to rebuild Chroma vectors.
3. No prompt changes; classifier re-embeds canonicals at startup.

**Swapping LLM provider:**
1. Update `LLM_PROVIDER` + `LLM_MODEL`.
2. No prompt changes (prompts are provider-agnostic).
3. Streaming adapter must implement both `complete` and `stream`.

**Tuning answer quality:**
- First stop is `rag_prompts.py` — identity voice, evidence rules,
  per-intent format rules, few-shots.
- Bump `PROMPT_VERSION` when editing so telemetry correlates.
- Run `make eval-intent` after any classifier/canonicals change.
- Manual regression spot-checks against the fixture corpus before
  shipping.
