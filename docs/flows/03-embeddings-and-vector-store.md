# 03 · Embeddings & vector store

How chunk text becomes vectors, where those vectors live, how we
search them, and what happens when the model changes.

---

## Purpose

Translate the chunker's output into a dense-vector index that supports
sub-100ms cosine similarity search. Isolate the embedding model behind
a Protocol so model swaps are configuration changes, not refactors.

---

## Flow

### Indexing (at ingest time)

```
list[Chunk] (with optional .context)
    │
    ▼
EmbeddingService.index_document (services/embedding_service.py:39)
    │  text_for_embedding  = [_text_for_embedding(c) for c in chunks]   # context+text
    │  text_for_display    = [c.text for c in chunks]                   # plain
    │  metadatas           = _build_metadatas(doc, chunks)
    │  embeddings          = _embedder.embed_documents(text_for_embedding)
    │
    ▼
ChromaVectorStore.upsert (adapters/chroma_store.py:170)
    │  _delete_by_document_id(document_id)   # clean re-index
    │  ids = ["{doc_id}:{i}" for i in range(len(chunks))]
    │  (embeddings supplied by the service; embed not re-run here)
    │
    │  batch-add in groups of 500:
    │    collection.add(
    │      ids=..., documents=text_for_display,
    │      metadatas=..., embeddings=...)
    ▼
ChromaDB
  collection: documents_<model_slug>   e.g. documents_bge_small_en_v1_5
  per-chunk metadata:
    always:  document_id, owner_id, chunk_index, total_chunks,
             chunking_version, filename, mime_type, has_context
    if set:  document_type, skills (joined), experience_years   (doc-level,
             only when present in doc.metadata_)
    from chunk.metadata (non-None only): chunk_kind, section_heading,
             page_number, element_kinds
    context (only when has_context is true)
```

`index_document` also writes one mean-pooled doc-level vector into
`documents_whole_<model_slug>` (F89.c) — see `10-similarity-search.md`.

The embedder is `SentenceTransformerEmbedder` (`sentence_transformer.py`)
by default, but swappable via `get_embedding_provider(settings)` in
`adapters/embeddings/registry.py`. Model load is lazy + thread-safe
(`_ensure_loaded` at :135).

### Query (at search time)

```
query_text + optional where clause
    │
    ▼
ChromaVectorStore.query (adapters/chroma_store.py:234)
    │  query_embedding = _embedder.embed_query(text)
    │  collection.query(query_embeddings=[...], n_results=N, where=...)
    │
    ▼
list[VectorHit]   chunk_id, document_id, text, metadata, distance
```

Distance is cosine; lower is better. `SearchService._vector_search`
drops anything above the model's `recommended_distance_threshold`
(`sentence_transformer.py::_MODEL_DISTANCE_THRESHOLDS`).

---

## Per-model collection naming

`ChromaVectorStore.__init__` builds the collection name as
`documents_<safe_collection_suffix(model_name)>`. That means:

- `BAAI/bge-small-en-v1.5` → `documents_bge_small_en_v1_5`
- `intfloat/e5-base-v2` → `documents_e5_base_v2`

Two models can live side-by-side in the same Chroma instance without
colliding. Flipping `EMBEDDING_MODEL` points the service at a *different*
collection; the old one stays until explicitly deleted.

Collection metadata includes `hnsw:space="cosine"` (Chroma's
similarity metric) and `embedding_model=<name>` — the startup
integrity log (`_log_startup_integrity` at :131) warns if the
collection's stored model disagrees with the one the adapter was
constructed with.

### Three collections per model

A single `ChromaVectorStore` owns three collections, all suffixed
with the same model slug and kept isolated so a query against one
never surfaces rows from another:

| Collection | Granularity | Written by | Read by |
|------------|-------------|------------|---------|
| `documents_<slug>` | one row per chunk | `index_document` → `upsert` | hybrid search vector lane |
| `documents_whole_<slug>` | one mean-pooled vector per doc (F89.c) | `upsert_document_vector` | `find_similar_documents` (`10`) |
| `candidates_<slug>` | one recruiter-brief vector per candidate (F104.a) | `upsert_candidate_summary` | `query_candidate_summaries` (RAG candidate lane) |

The candidate collection (`chroma_store.py:97`) implements a third
Protocol, `CandidateSimilarityStore` —
`upsert_candidate_summary` / `query_candidate_summaries` /
`delete_candidate_summary`. Its embedding text is the F104.a
recruiter brief, embedded with the same `EmbeddingProvider` so
distances stay comparable, though the candidate RAG lane applies its
own per-lane distance cutoff.

---

## Distance thresholds (F85.d)

`SentenceTransformerEmbedder.recommended_distance_threshold` reads a
per-model table:

| Family | Models | Threshold |
|--------|--------|-----------|
| BGE | `bge-small/base/large-en-v1.5` | 0.35 |
| MiniLM / MPNet | `all-MiniLM-L6-v2`, `all-mpnet-base-v2`, … | 0.60 |
| E5 | `e5-small/base/large-v2` | 0.50 |
| Nomic | `nomic-embed-text-v1.5` | 0.45 |
| Jina v2 | `jina-embeddings-v2-base-en` | 0.40 |
| Unknown | * | 0.50 (+ WARN) |

`SearchService._resolve_distance_threshold` uses this when
`SEARCH_MAX_DISTANCE=None` (default); an explicit env-var override
still wins.

**Why it matters**: swap embedder without updating the threshold and
you either exclude relevant hits (too tight) or poison results with
noise (too loose). The table decouples model choice from retrieval
correctness.

---

## Versioning

Every indexed document carries three version stamps in Postgres:

| Column | Bumped when |
|--------|-------------|
| `extraction_version` | Extractor output shape changes. Currently `v2-unstructured`. |
| `chunking_version` | Chunker rules change. Currently `v3-heading-as-metadata`. |
| `embedding_model_version` | Embedder model changes. Free-form (e.g. `BAAI/bge-small-en-v1.5`). |

Chunk-level metadata carries `chunking_version` too — lets retrieval
detect mixed-version corpora if we ever want to.

### Re-index scripts

| Script | What it does | When to run |
|--------|--------------|-------------|
| `scripts/reindex_embeddings.py` | Re-embed from persisted `document_elements`. No re-extract. | After `EMBEDDING_MODEL` swap. |
| `scripts/reextract_all.py` | Flip all non-pending docs to PENDING, re-enqueue extraction. | After `CHUNKING_VERSION` or `EXTRACTION_VERSION` bump. |

Targeted re-index (only `embedding_model_version != current`) isn't
scripted yet — see improvements below.

---

## Configuration knobs

| Setting | Default | Effect |
|---------|---------|--------|
| `EMBEDDING_PROVIDER` | `local` | Picks `EmbeddingProvider` implementation (only `local` today). |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | HF model id; drives collection name + threshold. |
| `EMBEDDING_DEVICE` | `None` (auto) | `cuda` / `mps` / `cpu`. |
| `SEARCH_MAX_DISTANCE` | `None` | Override the embedder's recommended threshold. |
| `CHROMA_HOST` / `CHROMA_PORT` | `localhost:8000` | ChromaDB server. |

---

## Known issues / pain points

1. **Startup crashes when Chroma is down.** Module-level singleton in
   `api/deps.py:105` wraps the constructor in try/except → `None` →
   `get_rag_service` returns `None`. But `SearchService` is still
   constructed with `_vector_store=None`, and `_vector_search` then
   silently returns empty hits. Ops see "search works but returns
   nothing" without a clear signal.
2. **Collection metadata drift isn't auto-healed.** The startup
   integrity log warns when the collection's stored `embedding_model`
   doesn't match the configured embedder, but we don't offer a
   one-line command to fix — ops must remember
   `scripts/reindex_embeddings.py`.
3. **No dimension check at upsert time.** Chroma accepts any vector
   shape per collection; if an embedder change slips past the
   collection-naming barrier (same model name, different weights —
   e.g. pinned version vs latest), vectors of the wrong dimension
   can enter. Chroma errors at *query* time, not upsert. The stored
   `dimension` on the `EmbeddingProvider` Protocol exists but isn't
   compared against collection metadata.
4. **`embed_query` doesn't use query prefixes** even for instruct-tuned
   models (e5, nomic, instructor). F85.e is scoped for this; today
   those models are called raw and lose a meaningful chunk of their
   MTEB score.
5. **Context accumulation in chunk metadata is a Chroma string cost.**
   Every chunk carries `filename`, `document_type`, `skills` (joined),
   etc. — effectively a row-level denormalization because Chroma's
   filters operate only on chunk metadata. Makes storage roughly ~2x
   what it would be with a join model. Acceptable today; worth
   noting for scale discussions.
6. **Per-document whole-doc vector now exists (F89.c shipped).**
   `DocumentSimilarityStore` + a second Chroma collection
   (`documents_whole_<model>`) hold one mean-pooled vector per doc.
   Chunk collection still can't answer "similar docs" on its own;
   the similarity path uses the separate collection. See
   `10-similarity-search.md`.
7. **Lazy load hides first-request latency.** First `embed_*` call in
   a fresh process takes seconds (model download / load). If the
   first request after a restart happens to be a RAG query, that
   latency is user-visible.
8. **`embed_documents` returns `list[list[float]]` but tests have
   caught callers passing numpy arrays** — implicit list conversion
   works but silently re-allocates. Low priority; flag if it shows up
   in profiles.
9. **No background re-embed for model-version mismatches.** If
   `embedding_model_version` differs from config, the doc's search
   quality silently degrades until someone remembers the script.
   Especially painful after a partial `reindex_embeddings.py` run.
10. **Chunks for deleted Chroma documents can outlive Postgres.**
    The delete path in `ChromaVectorStore.delete` is called from
    `DocumentService.delete` (`services/document_service.py:94`) but
    any orphaning (e.g. a failed delete that didn't raise, a
    collection reset) leaves stale chunks. `SearchService.
    _drop_orphan_vector_hits` (`search_service.py:735`) catches this
    at query time — good defense, but the underlying drift is
    invisible.

---

## Improvement opportunities

### Short-term

- **Startup health signal** for the vector store. If `_vector_store`
  is `None` at boot, the `/health` endpoint should report
  `vector_store: down`; today callers discover via empty results.
- **Dimension-check on upsert.** Compare `embedder.dimension` to
  the stored `collection.metadata['embedding_dim']` (add it as a
  stamp when creating the collection). Fail loud instead of letting
  malformed vectors accumulate.
- **Targeted re-embed script.** `scripts/reembed_stale.py` — query
  `documents where embedding_model_version != settings.embedding_model`,
  re-embed just those. Operationally much friendlier after model A/B.
- **Pre-warm embedder** on worker + API startup behind a `PREWARM=true`
  env flag. Move the lazy-load cost off the first user request.

### Medium-term

- **E5/Nomic query prefixes (F85.e).** Wrap `embed_query` /
  `embed_documents` with model-aware prefixes. Protocol supports it;
  implementations just need a `_query_prefix` / `_passage_prefix`
  pair per model. Waiting on F85.b model exploration that actually
  picks an instruct model.
- **~~F89.c doc-level vector store~~** — shipped. Second collection
  + `DocumentSimilarityStore` Protocol + `POST /documents/{id}/similar`
  all live. See `10-similarity-search.md`. Next step is the
  `similarity_max_distance` threshold once real usage gives us a
  distance distribution to tune against.
- **Eviction strategy for old collections.** When `EMBEDDING_MODEL`
  changes, the old collection is still live — lets us A/B. Once a
  new model is blessed, we need a "drop older collection" step so
  storage doesn't grow unbounded.
- **Matryoshka-dim shrink for nomic/mxbai.** Supported dimensionality
  reduction without re-embedding. Lets us trade quality for storage
  without re-indexing.

### Long-term

- **Adapter consolidation with pgvector.** At some corpus size the
  operational cost of a separate Chroma process outweighs its
  conveniences; pgvector keeps vectors + metadata + joins in one
  store. `VectorStore` Protocol supports it — would be a new adapter
  that points at Postgres.
- **Per-tenant collection sharding** if we move to multi-org SaaS.
  Today owner scoping is via `where owner_id=X` at query time; at
  scale a per-tenant collection (or per-tenant HNSW index) would
  cut query cost and simplify deletion.
- **Hybrid sparse-dense indexing.** BGE-M3 / SPLADE produce sparse
  vectors good for lexical-like semantics in vector space. Could
  replace or complement the FTS path once corpus grows enough to
  justify the added index.

---

## Cross-references

- **Code**: `backend/app/adapters/embeddings/sentence_transformer.py`,
  `app/adapters/embeddings/registry.py`, `app/adapters/chroma_store.py`,
  `app/services/embedding_service.py`,
  `backend/scripts/reindex_embeddings.py`.
- **Upstream**: `02-chunking-and-contextualization.md`.
- **Downstream**: `06-hybrid-search.md`, `08-rag-pipeline.md`.
- **Design**: `docs/features.md` F85.*, `docs/rag-pipeline.md` §5.
