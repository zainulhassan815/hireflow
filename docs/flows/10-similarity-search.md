# 10 · Similarity search (F89.c)

`POST /api/documents/{document_id}/similar` — "find more docs like
this one." Shipped (F89.c `[x]`); this doc describes the running
system.

---

## Purpose

Unlock workflows like:

- "This candidate is a perfect fit — find me 5 more like them."
- "This contract is a known-good template — which other contracts
  look similar?"
- "Which reports are structurally close to this quarterly?"

Distinct from the chunk-level retrieval that powers `/search` and
`/rag/*`: the unit is the whole document, not a passage inside it.

---

## Flow

### Request path

```
POST /api/documents/{document_id}/similar { limit: 1..50 }
    │
    ▼
routes/documents.py::find_similar_documents  (documents.py:277)
    │
    ▼
SearchService.find_similar_documents  (services/search_service.py:539)
    │
    │  1. 503 if _similarity_store is None (ChromaDB down at boot)
    │
    │  2. Fetch source doc via DocumentRepository.get
    │       - None                    → 404  NotFound
    │       - other owner (HR only)   → 403  Forbidden
    │       - status != READY         → 404  NotFound  (don't leak
    │                                         status across ownership
    │                                         boundary)
    │
    │  3. Build Chroma `where`:
    │       HR    → { owner_id: str(actor.id) }
    │       admin → None (cross-owner)
    │
    │  4. similarity_store.find_similar_documents(
    │        source_document_id,
    │        n_results = limit + 1,      ← over-fetch by 1 to drop self
    │        where = ...
    │     )
    │       raises DocumentNotIndexed  → 404  (distinct code:
    │                                          "document_not_indexed"
    │                                          → advise re-index)
    │
    │  5. Drop source doc from hits (filter BEFORE truncate).
    │       HNSW is approximate; source might not be top-1 every time.
    │       Exclude-then-truncate is the only safe pattern.
    │
    │  6. Hydrate via DocumentRepository.get_many(neighbour_ids):
    │       - drop rows missing from Postgres (drift safety, mirrors
    │         F86.c chunk-path)
    │       - drop non-READY docs
    │       - drop cross-owner docs even if Chroma `where` already did
    │         (belt-and-braces — stale metadata must never be the thing
    │          that breaks tenant isolation)
    │
    │  7. distance → similarity = max(0.0, 1.0 - distance)
    │     (cosine space; 1.0 = identical, 0.0 = unrelated)
    │
    │  8. break at limit
    ▼
list[SimilarDocument]   document_id, filename, document_type,
                        similarity, metadata
```

### Index path (runs for every doc reaching `READY`)

```
ExtractionService.process
    │
    ▼
EmbeddingService.index_document  (services/embedding_service.py:39)
    │
    │  chunks = chunk_elements(...)  +  LlmChunkContextualizer
    │
    │  embeddings = embedder.embed_documents(texts_for_embedding)  ── embed ONCE
    │
    │  vector_store.upsert(
    │      str(doc.id),
    │      texts_for_display,
    │      metadatas,
    │      embedding_texts = ...,
    │      embeddings = embeddings,     ← F89.c: reuse, skip internal embed
    │  )
    │
    │  if similarity_store is not None:
    │      pooled = pool_document_embedding(embeddings)   ← services/document_vector.py
    │      similarity_store.upsert_document_vector(
    │          str(doc.id),
    │          pooled,
    │          { document_id, owner_id, document_type? },
    │      )
    │
    │  doc.chunking_version = CHUNKING_VERSION
    │  doc.embedding_model_version = embedder.model_name
```

### Delete path

```
DocumentService.delete  (services/document_service.py:92)
    │
    ├── MinIO: delete blob
    ├── vector_store.delete(doc.id)                        ← chunks
    └── similarity_store.delete_document_vector(doc.id)    ← doc-level
```

Plus `EmbeddingService.remove_document` mirrors the same pair for
worker-side call sites.

---

## Doc-level representation — mean-pool

`services/document_vector.py::pool_document_embedding` — pure
function, ~40 lines.

```
pool_document_embedding(chunk_embeddings: list[list[float]]) -> list[float]
    - raises on empty input, zero dim, ragged shapes, zero-norm pool
    - mean = sum(vectors) / N
    - L2-normalise mean so the result is a unit vector on the same
      sphere as chunk + query vectors
    - returns list[float]
```

Why mean-pool vs alternatives:

| Option | Verdict |
|---|---|
| A. Re-embed full doc text | Truncates beyond 512 tokens (bge-small limit); wastes chunk work. |
| **B. Mean-pool chunk embeddings** | **Picked.** Zero new embedding calls; respects F82.c contextualized chunks; stable across re-indexes. |
| C. LLM-summarize then embed | Adds LLM dependency to indexing; expensive; semantics drift per summarizer. |

Weakness: loses chunk ordering; gets dominated by repetitive
boilerplate (footers, shared headers). Upgrade path (TF-IDF pool or
LLM summary) sits under the same Protocol — no API change when we
need it.

---

## Storage — second Chroma collection

Name: `documents_whole_<model_slug>` — derived from the embedder's
model name. E.g. `documents_whole_bge_small_en_v1_5`.

| | Chunk collection | Whole-doc collection |
|---|------------------|----------------------|
| Prefix | `documents_` | `documents_whole_` |
| Unit | one vector per chunk | one vector per doc |
| Id | `{doc_id}:{chunk_index}` | `{doc_id}` |
| Metadata | `document_id`, `owner_id`, `chunk_kind`, `section_heading`, etc. | `document_id`, `owner_id`, `document_type` |
| Space | `cosine` | `cosine` |

Separate collection — **not** a namespaced id inside the chunk
collection. Mixing doc-level + chunk-level vectors would force
post-filter plumbing on every chunk query; extra Chroma collections
are free, filter shims aren't.

Startup integrity log now reports both counts:

```
ChromaVectorStore ready:
  collection=documents_bge_small_en_v1_5 model=... chunks=289
  whole-doc-collection=documents_whole_bge_small_en_v1_5 documents=9
```

---

## Protocols

`adapters/protocols.py` — one Protocol per capability:

```python
@dataclass(frozen=True, slots=True)
class SimilarDocumentHit:
    document_id: str
    distance: float
    metadata: dict[str, Any]


@runtime_checkable
class DocumentSimilarityStore(Protocol):
    def upsert_document_vector(
        self, document_id: str, embedding: list[float],
        metadata: dict[str, Any],
    ) -> None: ...

    def delete_document_vector(self, document_id: str) -> None: ...

    def find_similar_documents(
        self, source_document_id: str, n_results: int,
        where: dict[str, Any] | None = None,
    ) -> list[SimilarDocumentHit]: ...
```

`VectorStore.upsert` grew one optional kwarg
(`embeddings: list[list[float]] | None`) so services can pre-compute
vectors once and feed both stores. Pre-F89.c call sites that pass
`embeddings=None` still work unchanged.

`ChromaVectorStore` implements both Protocols. Composition root
(`api/deps.py:105-114`) constructs **one** instance and binds it
under two typed slots (`_vector_store`, `_similarity_store`) so
services receive narrow Protocols without isinstance gymnastics.

---

## Wire contract

### Request — `SimilarDocumentsRequest`

```json
{ "limit": 10 }      // 1..50, default 10
```

### Response — `SimilarDocumentsResponse`

```json
{
  "source_document_id": "…",
  "results": [
    {
      "document_id": "…",
      "filename": "senior_engineer_resume.pdf",
      "document_type": "resume",
      "similarity": 0.87,
      "metadata": { "skills": [...], "experience_years": 8 }
    }
  ]
}
```

`similarity` is `max(0.0, 1.0 - cosine_distance)` — 1.0 = identical,
0.0 = unrelated. Keeps the UX-facing number in the natural "higher
is better" direction.

### Status codes

| Status | When | Body |
|---|---|---|
| 200 | Normal response (results may be empty) | `SimilarDocumentsResponse` |
| 401 | Not authenticated | `ErrorResponse` |
| 403 | Source doc owned by another user (HR) | `ErrorResponse` |
| 404 | Source missing / non-READY / no vector | `ErrorResponse` with `code="not_found"` OR `code="document_not_indexed"` |
| 422 | `limit` outside 1..50 | FastAPI validation |
| 503 | Chroma down at boot; similarity store `None` | `ErrorResponse` |

`DocumentNotIndexed` vs `NotFound` separate codes matter — the UI
can show "re-upload or wait for re-index" vs "this doc doesn't
exist" without parsing messages.

---

## Composition wiring

`api/deps.py` — at module load:

```python
_chroma_store = ChromaVectorStore(...)
_vector_store: VectorStore | None = _chroma_store
_similarity_store: DocumentSimilarityStore | None = _chroma_store
```

Wired into services:

- `DocumentService` — for the delete path (`deps.py:317-323`).
- `SearchService` — main consumer for `find_similar_documents`
  (`deps.py:342-348`).
- RAG `SearchService`-as-retriever (`deps.py:365-370`) — unused there
  but passed for symmetry.

`EmbeddingService` takes the embedder + optional similarity store
(constructed in `worker/tasks.py:77-81` and
`scripts/reindex_embeddings.py:71`).

---

## Configuration knobs

| Setting | Default | Effect |
|---|---|---|
| (embedder reused — no dedicated similarity model) | — | `embedding_model` drives the whole-doc collection suffix too. |
| `similarity_max_distance` | **not implemented** | Follow-up — distance distribution from real usage will drive the tune. |

Request-level knob:

| Field | Range | Default |
|---|---|---|
| `limit` | 1..50 | 10 |

---

## Key invariants

- **The source is always excluded**, never assumed to be top-1.
  HNSW recall is approximate; excluding-by-id handles "source was
  ranked 3rd against itself" uniformly with "source was ranked 1st."
- **Exclude before truncate.** Over-fetch by 1 (`limit + 1`), drop
  source, take `limit`. If we truncated first and excluded second
  the user could see fewer results than they asked for.
- **Non-READY neighbours are dropped post-hydrate.** Matches the
  F86.c chunk-path defense: metadata in Chroma can outlive Postgres
  state, so Postgres is authoritative.
- **Owner filter runs twice**: Chroma `where` clause + post-hydrate
  UUID compare. Redundant by design — Chroma metadata drift
  (reassigned docs) must never be the thing that breaks isolation.
- **`DocumentNotIndexed` ≠ `NotFound`.** Separating them lets the
  client distinguish "source legit but needs re-index" from "source
  doesn't exist." Distinct HTTP status + error code.
- **Embed once, reuse twice.** Service-layer embedding (F89.c moved
  the `embedder` from the adapter to `EmbeddingService`) means chunk
  upsert and doc-level pool share the same vectors. No second pass
  through the model.
- **`similarity_store is None` → 503 at request time.** Chroma down
  at boot → both `_vector_store` and `_similarity_store` go None
  together; similarity endpoint surfaces the right error instead of
  silently returning empty.

---

## Known issues / pain points

1. **No distance / similarity threshold.** Mean-pool cosine
   distances live in a different regime than chunk distances, so
   F85.d's `search_max_distance` doesn't transfer. Today the
   endpoint returns the top-K no matter how dissimilar — "similar"
   can mean 0.95 or 0.42. Tracked as follow-up.
2. **Mean-pool dominated by boilerplate.** Docs with heavy shared
   footers / disclaimer pages cluster on the boilerplate rather
   than substance. Known weakness; acceptable for shipping, worth
   fixing at corpus scale.
3. **No doc-type filter on the endpoint.** "Find similar resumes to
   this resume" currently includes reports, contracts, etc. if
   they're close in mean-pool space. Adding a `document_type`
   filter on the request (folding into the Chroma `where`) is a
   trivial extension.
4. **Re-index window leaves the endpoint empty.**
   `scripts/reindex_embeddings.py` deletes + recreates BOTH
   collections; until the per-doc loop finishes, similarity
   returns empty / `document_not_indexed`. Same pattern as the
   chunk path; documented; no fix planned.
5. **Zero-text docs aren't indexed.** `index_document` early-returns
   on empty elements / empty chunks; the doc-level vector is also
   never created. `/similar` on such a doc surfaces
   `document_not_indexed`. Correct behaviour, slightly confusing
   UX.
6. **Pre-F89.c docs need re-indexing.** Anything uploaded before
   the F89.c ship has no doc-level vector. Endpoint returns
   `document_not_indexed` until the operator runs
   `scripts/reindex_embeddings.py`. No automatic backfill.
7. **Chroma numpy-truthiness trap (now guarded).** The fetch path
   checks `raw is None or len(raw) == 0` rather than
   `raw or []` — a populated numpy array would otherwise raise
   `ValueError: truth value of an array with more than one
   element is ambiguous`. Worth remembering when extending the
   adapter.
8. **`find_similar_documents` doesn't pre-filter `where` on doc
   type / date**. The service only scopes by owner; any doc type
   filter would have to live in the Chroma `where` clause OR in a
   post-hydrate pass. Service signature is tight today; adding
   filters means widening it.
9. **No reranker on doc-level results.** A cross-encoder can't
   easily read a whole doc (512-token limit), so running the F80.5
   reranker here doesn't fit. Cosine-only ordering is slightly
   noisier than chunk-level would suggest.
10. **Metadata returned inside results is dict-shaped.** OpenAPI
    emits `dict[str, Any]`, which generates `unknown` in the
    TypeScript SDK. Frontend has to narrow at use sites. Same
    pattern as document-metadata elsewhere; minor type-safety gap.
11. **Approximate-NN ordering depends on HNSW params.** Chroma's
    default is good for our scale; at 100k+ docs we might need to
    tune `ef_search` for recall. Not user-visible today.
12. **No per-doc cap on call rate.** A user could repeatedly hit
    `/similar` for a popular doc; every call is a single Chroma
    query (fast). Worth a rate limit once the endpoint is UI-
    exposed.

---

## Improvement opportunities

### Short-term

- **Add `settings.similarity_max_distance`** (default `None`).
  Log distance distribution from real usage for a week, tune the
  cutoff based on the "noise band" observed, apply in
  `SearchService.find_similar_documents` before hydration.
- **Doc-type filter on the request.** Add `document_type:
  DocumentType | None` to `SimilarDocumentsRequest`; fold into the
  Chroma `where` clause. Unlocks "similar *resumes*" without
  cross-type contamination.
- **Exclude low-signal chunks from the pool.** Skip tiny list
  items, header-only chunks, and (eventually) F82.b doc-level
  chunks when computing the mean. Reduces boilerplate dominance.
- **Backfill warning in startup log.** Log the count of
  `documents where status=READY` that are missing from the
  whole-doc collection (via a single count comparison) so
  operators see the "N docs need re-index" signal without hitting
  the endpoint.
- **Frontend integration** — "Find similar" chip on the document
  detail view. Pairs with `F92.x` design work. Separate slice.

### Medium-term

- **TF-IDF-weighted pool.** Weight each chunk vector by its token
  IDF in the corpus when pooling. Same Protocol; drops boilerplate
  dominance materially without an LLM.
- **Diversity cap (MMR).** Post-query reorder so the top-K aren't
  near-duplicates of each other. Cheap; useful when a user has
  multiple versions of the same CV.
- **Explain "why similar".** For each hit, run one chunk-level
  retrieval with the source doc as the query against the hit, and
  return the top overlapping chunks. Gives users a "these passages
  line up" affordance.
- **Targeted re-index script.** Today
  `scripts/reindex_embeddings.py` rebuilds everything. Add a
  `--only-missing-similarity` flag that iterates docs whose
  `document_id` isn't in the whole-doc collection and only pools
  those. Pairs with the backfill warning.
- **Similarity as a retrieval signal for candidate matching.**
  `MatchingService._get_vector_scores` queries the chunk collection
  with `"{job.title} {job.description}"`. Pooling the job-side
  text through the same flow (or storing job-level vectors in a
  new slot) would unlock "rank candidates by whole-doc similarity
  to the JD," complementing the current chunk-level signal.

### Long-term

- **LLM-summary representation.** Pool replaces with a 2-paragraph
  LLM-generated summary embedded once per doc. Cleaner semantics;
  cost scales with corpus. Can A/B under the existing Protocol.
- **Hybrid similarity.** Doc-level cosine + metadata similarity
  (skill Jaccard, doc-type match, experience proximity) combined
  via weighted RRF — mirrors the chunk-side pipeline.
- **"Find similar to this query"** from a search input, not a doc.
  Same pool + collection; just takes a query string, embeds it,
  queries the whole-doc collection. Cheap addition once the UX
  surface exists.
- **Doc-level eval harness.** Golden pairs of "these two docs
  should rank close / these two should rank far" → regression
  signal on pool-method changes. Today we have chunk-level +
  intent + parser harnesses; similarity is the last unmeasured
  axis.

---

## Cross-references

- **Code**: `backend/app/adapters/chroma_store.py` (doc-level
  methods + second collection),
  `app/adapters/protocols.py::DocumentSimilarityStore,
  SimilarDocumentHit`,
  `app/services/document_vector.py::pool_document_embedding`,
  `app/services/embedding_service.py` (service-layer embedding +
  doc-level upsert hook),
  `app/services/search_service.py::find_similar_documents`,
  `app/api/routes/documents.py::find_similar_documents`,
  `app/schemas/document.py::SimilarDocumentsRequest / Response`,
  `app/domain/exceptions.py::DocumentNotIndexed`,
  `app/api/deps.py` (composition root),
  `backend/scripts/reindex_embeddings.py` (rebuilds both
  collections),
  `app/worker/tasks.py:77-81` (worker-side wiring).
- **Tests**: `tests/test_document_vector.py`,
  `tests/test_search_service_find_similar.py`,
  `tests/test_embedding_service.py`,
  `tests/test_documents_similar_endpoint.py`.
- **Dev docs**: `docs/dev/F89c-similarity-search/01-plan.md`,
  `02-plan-review.md`, `03-implementation-review.md`,
  `04-manual-test.md`, `05-summary.md`.
- **Related flows**: `01-document-upload-and-processing.md`
  (pool hook fires on READY), `03-embeddings-and-vector-store.md`
  (shared embedder + per-model collection),
  `09-candidate-matching.md` (same vector store, chunk-side query).
- **Design**: `docs/features.md` F89.c (shipped).
