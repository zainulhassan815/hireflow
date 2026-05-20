# Flow deep-dives

End-to-end traces of Hireflow's key features, focused on **how each step
is implemented today**, the **issues we already know about**, and the
**improvements** that would raise accuracy / robustness.

These docs are **isolated from the existing design docs on purpose**.
They're not another architecture overview — `docs/architecture.md`,
`docs/rag-system.md`, `docs/rag-pipeline.md`, `docs/search-hardening.md`
remain canonical for *design intent*. This folder is the lens that
looks at the *running system* and points at the next lever.

## Reading order

Start at `01` if you want the ingestion path. Jump to `08` if you want
RAG. The docs are independent but the numbering reflects data flow:

| # | Doc | Covers |
|---|-----|--------|
| 01 | [Document upload & processing](01-document-upload-and-processing.md) | HTTP upload → MinIO → Celery → extract → classify → persist → auto-candidate |
| 02 | [Chunking & contextualization](02-chunking-and-contextualization.md) | Element-aware chunker + F82.c LLM contextualizer |
| 03 | [Embeddings & vector store](03-embeddings-and-vector-store.md) | `EmbeddingProvider`, Chroma per-model collections, distance thresholds, re-index |
| 04 | [Lexical & fuzzy index](04-lexical-and-fuzzy-index.md) | `search_tsv`, weighted FTS, `pg_trgm` fallback, query normalization |
| 05 | [Query understanding](05-query-understanding.md) | Heuristic query parser (F89.a) + intent classifier (F81.g) + acronym/tech-token handling |
| 06 | [Hybrid search](06-hybrid-search.md) | `SearchService.search` end-to-end: parse → 4 signals → RRF → rerank → hydrate → highlight |
| 07 | [Reranker](07-reranker.md) | Cross-encoder reorder after RRF |
| 08 | [RAG Q&A pipeline](08-rag-pipeline.md) | `/rag/query` + `/rag/stream`: retrieval → context gate → intent → prompt → LLM → SSE |
| 09 | [Candidate ↔ job matching](09-candidate-matching.md) | `MatchingService` 3-signal score + ranking |
| 10 | [Similarity search](10-similarity-search.md) | F89.c "find more like this doc" — shipped |
| 11 | [Gmail sync](11-gmail-sync.md) | OAuth + claim-based dedup + stale recovery + pipeline handoff |
| 12 | [Frontend answer rendering](12-frontend-answer-rendering.md) | SSE consumer, markdown + citation chips, confidence badge |
| 13 | [Observability, eval & versioning](13-observability-eval-versioning.md) | Log lines, eval harness, version stamps, re-index scripts |

## What every doc contains

A fixed skeleton so you can scan any of them at the same speed:

1. **Purpose** — one paragraph on what this flow is and when it runs.
2. **Flow** — an ASCII diagram + step-by-step trace with `path:line`
   references into the code.
3. **Configuration knobs** — env vars / settings that affect behaviour.
4. **Known issues / pain points** — things that have bitten us, or
   edge cases we know are underhandled.
5. **Improvement opportunities** — short-term (low effort, clear win),
   medium-term (needs design), long-term (needs corpus/scale).
6. **Cross-references** — links to other flow docs + canonical design
   docs.

## What these docs are NOT

- Not another "what is RAG" tutorial — assumes familiarity with
  retrieval + LLMs.
- Not a tracker — the authoritative task list is
  `docs/features.md`. Improvement items here surface candidates;
  converting any into real work means adding an `FXX` entry there.
- Not a standard — conventions stay in `docs/conventions.md`,
  `docs/api-standards.md`, `docs/frontend-standards.md`.
- Not user docs — they target engineers touching the code.

## Where each flow lives in the code

| Area | Primary module(s) |
|------|-------------------|
| Upload / processing | `backend/app/api/routes/documents.py`, `app/worker/tasks.py::extract_document_text`, `app/services/extraction_service.py` |
| Text extraction | `app/adapters/text_extractors.py` |
| Classification | `app/adapters/classifiers/*`, `app/services/extraction_service.py::_classify` |
| Chunking | `app/services/chunking.py` |
| Contextualization | `app/adapters/contextualizers/llm.py` |
| Embeddings | `app/adapters/embeddings/sentence_transformer.py`, `app/services/embedding_service.py` |
| Vector store | `app/adapters/chroma_store.py` |
| FTS / fuzzy | `app/repositories/document.py`, Alembic migration `2347719a1bd8` |
| Query normalization | `app/services/query_expansion.py` |
| Query parsing | `app/services/query_parser.py`, `app/services/query_parser_vocab.py` |
| Intent classification | `app/services/intent_classifier.py`, `app/services/intent_canonicals.py` |
| Search orchestration | `app/services/search_service.py` |
| Reranker | `app/adapters/rerankers/cross_encoder.py` |
| RAG | `app/services/rag_service.py`, `app/services/rag_prompts.py`, `app/api/routes/rag.py` |
| Matching | `app/services/matching_service.py` |
| Gmail | `app/services/gmail_sync_service.py`, `app/adapters/gmail_*.py`, `app/worker/tasks.py` |
| Frontend chat | `frontend/src/pages/qa.tsx`, `frontend/src/api/rag-stream.ts` |

## Working against these docs

When you ship a change that alters behaviour described here:

- Update the relevant doc's **Flow** section and any affected issue
  entries *in the same PR*.
- If a listed improvement ships, move it to the **What changed**
  trailer at the bottom of the doc with the feature id.
- When an issue is closed, delete it — not "keep for history." The
  doc should describe the running system today, not its biography.

Same rule as the existing docs: truth in code, this doc catches up at
review time.
