# 02 · Chunking & contextualization

How typed elements turn into retrieval-ready chunks, and how each chunk
gets an optional LLM-generated "situating" context before it's embedded.

---

## Purpose

Produce chunks that are:

- **Semantically self-contained** enough to feed an LLM when retrieved.
- **Structured** — heading, page, element kinds travel with the chunk
  so retrieval and display can show context.
- **Sized** to fit the embedder and the downstream token budget.

Plus an optional pre-embed augmentation (F82.c): prepend a short
LLM-written context describing where this chunk sits in the document.
Helps retrieval when the chunk alone is ambiguous ("Q3 revenue
declined 4%" — which company? which quarter? contextualization
writes that in.)

Since F103.d the contextualizer is **entity-aware**: both the
summary and per-chunk prompts inject the document's resolved author
(`Document.authored_by.name`, falling back to `metadata['name']`)
and the classifier's extracted technology list, and instruct the LLM
to attribute work to the named author rather than stripping to
passive voice.

---

## Flow

Input: `list[Element]` from `UnstructuredExtractor` (typed layout
regions with `kind`, `text`, `page_number`, `order`, `metadata`).
Output: `list[Chunk]` with text + metadata + optional `context`.

```
elements (reading order)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  chunk_elements()  (services/chunking.py:61)                │
│                                                             │
│  if total_text ≤ 1500 chars → ONE tiny-doc chunk (:73)      │
│  else walk in reading order:                                │
│    - Title/Header kinds                                     │
│         flush narrative buffer, set current_heading = text  │
│         Heading itself NOT emitted as a chunk (v3 CHANGE)   │
│         — it lands on subsequent chunks as section_heading  │
│    - Table kinds                                            │
│         flush narrative buffer                              │
│         _table_chunk() — prefer HTML (metadata.text_as_html)│
│           over plain flattened cell text                    │
│    - NarrativeText / ListItem / everything else             │
│         append to narrative buffer                          │
│  at end: flush narrative buffer                             │
│                                                             │
│  _pack_narrative()  (:146)                                  │
│    greedy pack toward 1200 chars (TARGET)                   │
│    emit when > 1500 chars (SOFT MAX)                        │
│    oversize single element → sentence-split fallback         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
list[Chunk]   text, metadata{chunk_kind, section_heading,
              element_kinds, page_number}
    │
    ▼  (optional; only if LLM_PROVIDER configured)
┌─────────────────────────────────────────────────────────────┐
│  LlmChunkContextualizer.contextualize()                     │
│  (adapters/contextualizers/llm.py:187)                      │
│                                                             │
│  mode = auto | summary | full_doc                           │
│                                                             │
│  resolve author_clause + tech_clause once per doc:          │
│    author = doc.authored_by.name → metadata['name']         │
│             → "unknown"  (F103.d)                           │
│    tech   = metadata['skills'], comma-joined, capped at 50  │
│                                                             │
│  auto:                                                      │
│    len(doc.extracted_text) ≤ full_doc_max_chars (8000)      │
│      → "full_doc"  (prompt includes full doc body)          │
│    else → "summary" (one summary LLM call + per-chunk LLM)  │
│                                                             │
│  for each chunk:                                            │
│    _situate() — one LLM.complete call                       │
│      system: SITUATE_SYSTEM_PROMPT                          │
│      user: filename + author_clause + tech_clause +         │
│            doc_context + chunk.text                         │
│    on success → replace(chunk, context=text)                │
│    on failure → replace(chunk, context=None)   (non-fatal)  │
│                                                             │
│  stamp doc.metadata['contextualization_version'] =          │
│    "v2-haiku-entity-aware"  (F103.d)                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
list[Chunk]  (some / all with chunk.context populated)
```

Consumed by `EmbeddingService.index_document` in
`services/embedding_service.py:39`. There, `_text_for_embedding`
(:179) folds `context` into the embed text (`{context}\n\n{text}`)
while `text_for_display` stays as `chunk.text` only — context
moves the retrieval vector without leaking into snippets.

---

## Key invariants

- **Headings aren't chunks** in `CHUNKING_VERSION=v3-heading-as-metadata`.
  "SKILLS" alone embeds poorly and wastes a contextualizer call. Heading
  text lives as `section_heading` on every following narrative/table/list
  chunk until the next heading. Big retrieval win.
- **Table chunks prefer HTML** (`metadata.text_as_html`) when
  `UnstructuredExtractor` gave us a structured table. Keeps column
  relationships intact for the LLM to read. Plain flattened text
  survives when HTML wasn't available.
- **Per-chunk contextualization failures are non-fatal.** A broken
  context just means `context=None` and the chunk embeds as plain
  text — retrieval quality degrades gracefully rather than the whole
  doc failing to index.
- **Context only moves the vector, never the display.** `chunk.text`
  is what snippets + highlights see; `_text_for_embedding` is what
  the embedder sees. Keeps the UI honest.
- **Pure, deterministic chunker.** `chunk_elements` has no I/O or
  shared state. Same element list → same chunks every time — makes
  the eval harness stable across runs.

---

## Configuration knobs

Chunker — hardcoded in `services/chunking.py`:

| Constant | Value | Effect |
|----------|-------|--------|
| `_TARGET_CHARS` | 1200 | Greedy pack target. |
| `_MAX_CHARS_SOFT` | 1500 | Stop packing once past this. |
| `_TINY_DOC_THRESHOLD` | 1500 | Whole doc becomes one chunk below this. |
| `CHUNKING_VERSION` | `v3-heading-as-metadata` | Bumped when rules change → re-chunk required. |

Contextualizer — env-driven:

| Setting | Default | Effect |
|---------|---------|--------|
| `CONTEXTUALIZER_PROVIDER` | `llm` | `none` / `llm`. `none` turns F82.c off. |
| `CONTEXTUALIZER_MODE` | `auto` | `auto` / `summary` / `full_doc`. |
| `CONTEXTUALIZER_FULL_DOC_MAX_CHARS` | 8000 | Threshold for `auto` to pick `full_doc`. |
| `_SUMMARIZE_MAX_CHARS` | 30_000 (constant) | Cap summary prompt body. |
| `_MAX_SKILLS_IN_PROMPT` | 50 (constant) | Cap on the F103.d tech list injected into prompts. |

`contextualize()` stamps `metadata['contextualization_version']`
(currently `v2-haiku-entity-aware`) on the document after a successful
pass — a version marker a targeted re-embed can use to find
stale-prompt docs without a schema change.

---

## Known issues / pain points

1. **No element-level context in the HTML table chunk.** If a table
   sits under a heading *and* after narrative that defines an
   acronym, neither reaches the chunk. `section_heading` is
   attached but the LLM that reads the table won't see the
   paragraph above it that said "where NRR = Net Revenue Retention".
   F82.c's "full_doc" mode mitigates for small docs; doesn't help
   large ones where `summary` mode is picked.

2. **Contextualizer runs serially.** `adapters/contextualizers/llm.py:199`
   loops chunks, 1 LLM call each. For a 20-chunk doc in `full_doc`
   mode on Anthropic, that's ~10-20s wall-clock. Parallelism is a
   tradeoff against provider rate limits; today we just wait.

3. **Summary cache is per-document only** — if a doc has 30 chunks we
   do 1 summary call + 30 situate calls. That's right for one-off
   ingestion but means re-ingestion (F82.c prompt bumped) pays
   the full cost again. There's no `contexts` table persisting the
   result.

4. **Over/under-packing edge cases.** An element at `len(text) > 1500`
   hits `_split_oversized`, which sentence-splits then falls back to
   fixed-char slicing. Rare on resumes; legal contracts with long
   paragraphs hit this occasionally and produce slightly sub-optimal
   splits (mid-thought).

5. **Heading-only chunk exclusion loses orphan headings.** If a
   document's last heading has no following narrative, its text is
   dropped. Minor — usually indicates an extraction glitch — but
   silent.

6. **Tiny-doc shortcut misses structure.** A ≤1500 char doc collapses
   to one chunk with *the first* heading as `section_heading`.
   Multi-heading tiny docs (a one-page resume with SKILLS +
   EXPERIENCE + EDUCATION) end up with a single chunk whose
   `section_heading` is arbitrary.

7. **Contextualizer error signal is uninformative.** `per-chunk
   contextualization failed` appears in logs with the chunk index but
   not *why* (rate limit? malformed response? timeout?). Need to cross-
   reference the LLM adapter's translator (F81.i) — not hard, just
   annoying.

8. **`metadata.text_as_html` presence is library-version dependent.**
   Unstructured's table output varies across versions; if it
   regresses or stops emitting HTML, table chunks silently fall back
   to plain flattened text. We don't warn when this happens.

9. **No semantic chunking.** Hard char/element boundaries work well
   for resumes but split mid-thought in narrative-heavy docs. A
   sentence-embedding + semantic-similarity splitter would likely
   lift R@5 on the "find the section about X" queries.

---

## Improvement opportunities

### Short-term

- **Parallelize contextualizer calls** with a bounded concurrency
  (say 4). Drops wall-clock ~4x at indexing time; rate-limit risk
  is low at our ingest rate. Need to thread `asyncio` through; the
  sync `LLM.complete` path can still run via `to_thread`.
- **Log the reason for contextualization failures.** Take advantage
  of F81.i's `LlmProviderError` taxonomy — the adapter already knows
  if it was rate-limit vs timeout. Surface in the per-chunk WARN so
  ops can act on patterns.
- **Include preceding narrative in table chunks.** Prepend the last
  narrative paragraph above the table (if any) to the table chunk's
  `text` at chunk-assembly time. Cheap; fixes the "acronym defined
  above the table" miss.
- **F82.b whole-doc chunk**. Emit one `chunk_kind="document"` per doc
  with a concatenated distilled representation (first narrative +
  headings + skills). Unblocks broad "find me a persona" queries
  that no single 1200-char chunk can answer. Already scoped in
  `docs/features.md`.

### Medium-term

- **Persist contextualization results** in a `document_chunk_contexts`
  table keyed by `(document_id, chunk_index, context_version)`. Then
  re-index doesn't re-generate contexts unless the version changes.
  Pairs cleanly with the existing version-stamp pattern.
- **Multi-granularity chunks (F82.f)** — embed sentence, paragraph,
  and section as separate rows with a parent pointer. Retrieve
  small-return-big at query time. Complements the retrieval
  pipeline; requires chunker + vector-store work.
- **Semantic chunker** — split on sentence-embedding drift rather
  than char count. `langchain_experimental.text_splitter.SemanticChunker`
  is ~50 LOC; avoids mid-thought splits in reports / contracts where
  elements are large prose blocks.
- **Context caching observability**. Counter per doc for "contexts
  reused / regenerated" once persistence lands. Makes the F82.c cost
  model visible.
- **Heading promotion on orphan headings** — emit a lightweight
  `section_heading` carrier chunk when a heading has no following
  element, so the heading text still lives in the index.

### Long-term

- **Model-aware chunk sizing.** Embedder dimension + max-tokens drive
  `_TARGET_CHARS`. Today both are hardcoded. A small lookup table
  (similar to `_MODEL_DISTANCE_THRESHOLDS` in
  `sentence_transformer.py`) lets model swaps adjust chunk size
  without a code change.
- **Adaptive contextualization.** Skip contextualization on chunks
  whose `section_heading` + `text` are already dense (resume
  SKILLS section is fine as-is). Use a cheap heuristic (text length
  + keyword density) to decide per-chunk whether the LLM call is
  worth it.
- **Doc-type-specific chunkers.** Resumes want section-level chunks;
  contracts want clause-level; reports want heading-level. Route
  via `document_type` after classification, keep the default for
  "other". Prerequisites: classification accuracy (F84), eval fixtures
  per type.

---

## Cross-references

- **Code**: `backend/app/services/chunking.py`,
  `app/adapters/contextualizers/llm.py`,
  `app/services/embedding_service.py::_text_for_embedding`.
- **Upstream**: `01-document-upload-and-processing.md`.
- **Downstream**: `03-embeddings-and-vector-store.md`.
- **Design**: `docs/rag-pipeline.md` §1, `docs/features.md`
  F82.b/c/d/e/f.
