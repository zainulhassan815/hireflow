# 07 · Reranker

Cross-encoder reorder step that sits between RRF and the user-facing
result list. Used at both doc-level (`/search`) and chunk-level
(`/rag/*` via `retrieve_chunks`).

---

## Purpose

RRF merges diverse signal sources at rank granularity, which is good
for recall but noisy for precision — the top-K tends to be mostly
correct but the *order* within that window is shaky. A cross-encoder
(model attends over query + candidate text together) produces sharper
relevance scores per pair, at the cost of running inference per
candidate.

Keep the heavy model off the main retrieval path: only reshuffle the
top-K that RRF already nominated.

---

## Flow

```
merged RRF candidates (doc-level or chunk-level)
    │
    │   merge_limit = max(reranker_top_k, user_limit)    when reranker enabled
    │   (widen the candidate pool so rerank has room to reshuffle)
    │
    ▼
_rerank_results  (search_service.py:714)   |   _rerank_chunks (:630)
    │
    │  candidates = [
    │    RerankCandidate(
    │      document_id = doc.id,          # or chunk's doc_id + chunk_idx
    │      text = top highlight text,     # chunk-level: actual chunk text
    │      metadata = {"chunk_index": N}, # chunk-level only
    │    )
    │  ]
    │
    │  try:
    │    reranked = reranker.rerank(query, candidates, top_n=limit)
    │  except Exception:
    │    log + fall back to RRF order
    ▼
CrossEncoderReranker.rerank  (adapters/rerankers/cross_encoder.py:52)
    │
    │  model = _ensure_loaded()           # lazy one-time load
    │  pairs = [(query, c.text or "") for c in candidates]
    │  scores = model.predict(pairs)
    │
    │  sort(candidates, by score desc)
    │  if top_n set: truncate
    ▼
reranked list  (same RerankCandidate shape, fresh order)
    │
    ▼
(search)   map back to doc dicts by document_id
(RAG)      map back to RetrievedChunk by (document_id, chunk_index)
```

Default model: `BAAI/bge-reranker-base` (~280MB). Loads lazily on
first request; `threading.Lock` prevents double-init under concurrent
first-calls.

`NullReranker` is the fallback adapter when
`reranker_provider=none` or init fails — it returns candidates in
the same order so callers can always call `rerank()`.

---

## Why cross-encoder vs bi-encoder

- **Bi-encoder** (the embedder): `embed(query)` and `embed(doc)`
  independently, compare via cosine. Fast, cacheable, imprecise
  because the two texts never attend to each other.
- **Cross-encoder**: `forward(query, doc)` in one pass through a
  small transformer. Query tokens attend over doc tokens directly,
  producing a relevance score that captures subtle intent matching
  the bi-encoder misses.

Trade-off: bi-encoder scales (embed once, query millions); cross-
encoder is O(candidates × forward-pass cost). Running cross-encoder
on 20 candidates is cheap; on 20k would be painful.

---

## Ordering guarantees

1. **Reranked set ⊆ RRF candidates.** The reranker reorders, it
   doesn't fabricate. If a doc isn't in the top-K after RRF, the
   cross-encoder never sees it.
2. **Stable fallback.** Reranker exceptions log + return
   `results[:limit]` in RRF order. No silent degradation.
3. **Chunk-level mapping is by `(doc_id, chunk_index)`.** A doc
   contributing three chunks can end up with a different subset
   after rerank, and the relative order of the surviving chunks
   may not match RRF.

---

## Configuration knobs

| Setting | Default | Effect |
|---|---|---|
| `reranker_provider` | `local` | `local` loads the cross-encoder; `none` uses `NullReranker`. |
| `reranker_model` | `BAAI/bge-reranker-base` | HF model id. |
| `reranker_top_k` | 20 | Candidates handed to the reranker per query. |

`reranker_provider`, `reranker_model`, `reranker_top_k` are the only
real settings (`core/config.py`). `device` and `max_length` are
**constructor params on `CrossEncoderReranker`, not settings** — the
registry builds the reranker as
`CrossEncoderReranker(model_name=settings.reranker_model)` and never
passes them, so they're effectively hardcoded to `None` (auto device
selection) and `512` (tokenizer truncation per `(query, doc)` pair).
Making them tunable would mean adding settings + threading them
through the registry.

---

## Known issues / pain points

1. **Input text for doc-level rerank is top-1 highlight text.** If
   the RRF winner is a lexical match whose "top highlight" is a
   random chunk of body text, the cross-encoder sees that chunk —
   not the filename match that caused the win. Usually harmless;
   occasionally reranker downweights a correct result because the
   text it scored wasn't the matching evidence.
2. **Unbounded CPU inference on warm start.** Running
   `bge-reranker-base` on CPU is ~50-100ms for 20 candidates. Noticeable
   on cold CPU-only deployments; GPU deploys don't care.
3. **No warm-up.** First query after boot pays model-load (seconds)
   + first-predict (JIT). No `PREWARM` hook.
4. **Truncation at 512 tokens silently.** Chunks longer than 512
   tokens are truncated; the part beyond doesn't influence the
   score. Our chunks are ~1200 chars so usually under 512 tokens,
   but table-rich chunks can exceed it.
5. **Candidates from zero-text sources.** `_rerank_results` passes
   `c["filename"]` when `highlights` is empty — the cross-encoder
   scores a query against a filename, which is fine but not what
   it was trained on. Borderline fine for filename matches, odd for
   anything else.
6. **Exception path is blunt.** Any exception → full fallback to RRF
   order. A partial failure (one candidate's text missing) takes
   the whole batch down to RRF. Per-candidate error isolation would
   help; uncommon today.
7. **Chunk metadata mapping by `(doc_id, chunk_index)`** assumes the
   chunk_index is unique per doc. Holds today; would break if we
   ever ship sub-chunk IDs.
8. **No rerank-score persistence.** The score the cross-encoder
   assigns is computed but discarded after sorting. We can't debug
   "why did result X end up 4th after rerank" without rerunning.
9. **Reranker model is global.** Single provider, single model.
   A future choice of "fast local for browse + stronger hosted
   for serious queries" would need a second Protocol implementation.

---

## Improvement opportunities

### Short-term

- **Persist rerank scores.** Annotate each result with
  `rerank_score` internally (even if not on the wire). Makes
  triaging "why did this rank" trivial.
- **Use full chunk text for chunk-level rerank.** `_rerank_chunks`
  already passes `c.text`; confirm via tests it's the actual chunk
  not the snippet slice.
- **Warmup hook.** `/health?warmup=reranker` hits one predict on a
  dummy pair during deploy. Eats cold-start latency before the
  first real request.
- **Expose rerank score in `SearchResponse`** (optional field). Lets
  the frontend sort "by relevance" vs "by recency" without a second
  call.

### Medium-term

- **Per-query rerank budget.** `reranker_top_k` is global. A simple
  query gets the same 20 candidates as a complex one. Dynamically
  widen on low-confidence parses (lots of `runner_up` ambiguity →
  look at 50); tighten on high-confidence exact filters.
- **Two-stage rerank** for long queries — first pass with the
  cheap `ms-marco-MiniLM-L-6-v2`, second pass with `bge-reranker-base`
  on the top 5. Extra latency saved on the common "simple query"
  case.
- **Length-aware truncation.** If a chunk is 700 tokens, today it's
  silently clipped to 512. A smarter pipeline would query-focused
  truncate (keep the 512 tokens closest to query-term matches).
- **Rerank fail-stop metric.** Counter on how often rerank falls
  back; alert if >1% of queries. Lets us catch OOM / device hang
  without user reports.

### Long-term

- **Offline rerank eval loop.** Golden queries → measure MRR before/
  after rerank. Blocks merging a model change that regresses. Pairs
  with `tests/eval/test_search_quality.py`.
- **Distillation.** Fine-tune a smaller cross-encoder on rerank
  outputs of a larger hosted one. Keeps latency + cost low on our
  corpus-specific relevance.
- **Cross-encoder as retrieval primary at small scale.** Below ~10k
  docs, embedding + cross-encoder on everything might be tractable
  and more accurate than bi-encoder + rerank. Calibrate if we stay
  small.

---

## Cross-references

- **Code**: `backend/app/adapters/rerankers/cross_encoder.py`,
  `app/adapters/rerankers/null.py`,
  `app/adapters/rerankers/registry.py`,
  `app/services/search_service.py::_rerank_results`,
  `app/services/search_service.py::_rerank_chunks`.
- **Protocol**: `Reranker`, `RerankCandidate` in
  `adapters/protocols.py`.
- **Tests**: `tests/test_cross_encoder_reranker.py`.
- **Related flows**: `06-hybrid-search.md`, `08-rag-pipeline.md`.
- **Design**: `docs/features.md` F80.5, `docs/rag-system.md`
  §3 retrieval stack.
