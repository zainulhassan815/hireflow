"""Hybrid search: vector similarity + lexical FTS + metadata filtering.

Three retrieval signals contribute to the same RRF merge:

* **Vector** (``_vector_search``) — semantic similarity from ChromaDB,
  filtered to hits inside ``search_max_distance``. Chunk-level.
* **Lexical** (``_lexical_search``, F85) — Postgres FTS via
  ``ts_rank_cd`` over ``documents.extracted_text_tsv``. Catches
  single-word and exact-phrase queries that embeddings miss.
  Document-level.
* **SQL metadata** — only contributes when structured filters
  (``skills``, ``document_type``, etc.) are supplied; otherwise it
  would return "recent documents for any query".

F80 hardened the vector path (distance ceiling, no implicit metadata
path, raw RRF scores not normalized). F85 added the lexical path.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from app.adapters.protocols import (
    DocumentSimilarityStore,
    QueryParser,
    RerankCandidate,
    Reranker,
    RetrievedChunk,
    VectorHit,
    VectorStore,
)
from app.core.config import settings
from app.domain.exceptions import Forbidden, NotFound, ServiceUnavailable
from app.models import Document, DocumentStatus, DocumentType, User, UserRole
from app.repositories.document import DocumentRepository
from app.services.highlight import extract_query_terms, find_match_spans
from app.services.query_expansion import expand_acronyms, normalize_tech_tokens

logger = logging.getLogger(__name__)

_RRF_K = 60  # standard reciprocal rank fusion constant

Confidence = Literal["high", "medium", "low"]


@dataclass
class SearchResult:
    document_id: UUID
    score: float
    highlights: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SimilarDocument:
    """F89.c — one neighbour from ``find_similar_documents``.

    ``similarity`` is the UX-friendly cosine similarity (1.0 = identical,
    0.0 = orthogonal), derived from Chroma's cosine distance. Metadata
    carries whatever the Document row has (skills, experience_years, etc.)
    so the UI can show compact context without a second round-trip.
    """

    document_id: UUID
    filename: str
    document_type: DocumentType | None
    similarity: float
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchService:
    def __init__(
        self,
        documents: DocumentRepository,
        vector_store: VectorStore | None,
        reranker: Reranker | None = None,
        query_parser: QueryParser | None = None,
        similarity_store: DocumentSimilarityStore | None = None,
    ) -> None:
        self._documents = documents
        self._vector_store = vector_store
        self._reranker = reranker
        self._similarity_store = similarity_store
        # F89.a — NullQueryParser (empty-filter emitter) is a safe
        # default for legacy callers (test harnesses). Production
        # always injects HeuristicQueryParser via the composition root.
        if query_parser is None:
            from app.services.query_parser import NullQueryParser

            query_parser = NullQueryParser()
        self._query_parser = query_parser

    async def search(
        self,
        *,
        actor: User,
        query: str,
        document_type: DocumentType | None = None,
        skills: list[str] | None = None,
        min_experience_years: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 10,
    ) -> tuple[list[dict[str, Any]], int]:
        """Run hybrid search scoped to ``actor``. Returns (results, query_time_ms).

        Per-user scoping with admin bypass — same rule the documents
        routes use (`DocumentService._ensure_access`). HR users only see
        documents they own; admins see all. Enforced in every retrieval
        path (vector ``where`` filter, FTS query, SQL metadata path) so
        access control happens during retrieval, not as a post-filter
        that could leak metadata.
        """
        start = time.monotonic()

        # F88.a: skip every retrieval call on a no-op query rather than
        # paying for a roundtrip to ChromaDB and Postgres for zero hits.
        if not query.strip():
            return [], int((time.monotonic() - start) * 1000)

        # F89.a — parse NL into structured filters. User-provided
        # filters always win (explicit > implicit). Parsed filters
        # only fill gaps where the caller passed ``None``.
        #
        # Skills are only promoted to a filter alongside a strong
        # signal (years, seniority, doctype, dates). A standalone
        # skill mention could be either a filter or a semantic term
        # ("Python" vs "what is Python used for") — without a strong
        # signal to disambiguate, leave it to the semantic path.
        parsed = self._query_parser.parse(query)
        if document_type is None and parsed.filters.document_type:
            document_type = _document_type_from_str(parsed.filters.document_type)
        if min_experience_years is None:
            min_experience_years = parsed.filters.min_experience_years
        if date_from is None:
            date_from = parsed.filters.date_from
        if date_to is None:
            date_to = parsed.filters.date_to
        if not skills and parsed.filters.has_strong_filter and parsed.filters.skills:
            skills = list(parsed.filters.skills)

        owner_filter = None if actor.role == UserRole.ADMIN else actor.id

        vector_hits = self._vector_search(
            query, document_type, limit * 3, owner_id=owner_filter
        )

        # F86.c: vector chunks can outlive the docs they came from —
        # Chroma chunks for a deleted/reset doc that no longer exists in
        # Postgres, or for a doc demoted from READY. Those orphans collect
        # RRF score, dominate the merged top-K, and crowd out real lexical
        # hits. Filter them out before scoring so RRF only ranks docs we
        # can hydrate AND that are READY.
        vector_hits = await self._drop_orphan_vector_hits(vector_hits)

        has_structured_filter = any(
            [
                document_type is not None,
                bool(skills),
                min_experience_years is not None,
                date_from is not None,
                date_to is not None,
            ]
        )

        if has_structured_filter:
            sql_docs = await self._documents.search_by_metadata(
                document_type=document_type,
                skills=skills,
                min_experience_years=min_experience_years,
                date_from=date_from,
                date_to=date_to,
                limit=limit * 3,
                owner_id=owner_filter,
            )
        else:
            sql_docs = []

        # F88.b + F88.d: normalize the lexical query.
        # - normalize_tech_tokens preserves C++/C#/.NET/Node.js by
        #   substituting them with the same safe forms the index uses.
        # - expand_acronyms swaps K8s/ML/JS for canonical words.
        # Vector path keeps the raw query — embeddings already handle
        # both cases semantically; normalizing for them adds noise.
        lexical_query = expand_acronyms(normalize_tech_tokens(query))
        lexical_hits = await self._documents.full_text_search(
            lexical_query,
            limit=limit * 3,
            owner_id=owner_filter,
            document_type=document_type,
        )

        # F88.c: typo tolerance via trigram similarity on filename.
        # Fallback only — runs when FTS returns zero. Trigram is fuzzier
        # than FTS, so using it always would muddy good queries; using
        # it only on otherwise-empty results lets the user still find
        # docs with mistyped queries.
        if not lexical_hits:
            lexical_hits = await self._documents.fuzzy_search(
                query,
                limit=limit * 3,
                owner_id=owner_filter,
                document_type=document_type,
            )

        # Widen the merged set when a reranker is wired so the cross-
        # encoder has enough candidates to reshuffle meaningfully.
        # After rerank, we truncate back to the user's requested limit.
        merge_limit = max(settings.reranker_top_k, limit) if self._reranker else limit
        merged = self._rrf_merge(
            vector_hits,
            sql_docs,
            lexical_hits,
            merge_limit,
            w_vector=settings.rrf_weight_vector,
            w_sql=settings.rrf_weight_sql,
            w_lexical=settings.rrf_weight_lexical,
        )

        doc_ids = [m.document_id for m in merged]
        docs_map = await self._documents.get_many(doc_ids)

        # Annotate each highlight with the per-snippet match offsets
        # so the frontend can render ``<mark>`` without re-tokenizing.
        terms = extract_query_terms(query)
        for item in merged:
            for highlight in item.highlights:
                highlight["match_spans"] = find_match_spans(highlight["text"], terms)

        results = []
        for item in merged:
            doc = docs_map.get(item.document_id)
            if doc is None:
                continue
            # F86.b: vector chunks for a doc may exist in Chroma even when
            # the doc has since been demoted to PROCESSING/FAILED — chunk
            # metadata is set at index time and not refreshed on status
            # change. The FTS and SQL paths filter status at the query
            # level; we mirror that here so all three sources behave the
            # same. Architectural fix (don't index non-READY chunks at
            # all) is a follow-up on the extraction pipeline.
            if doc.status != DocumentStatus.READY:
                continue
            results.append(
                {
                    "document_id": doc.id,
                    "filename": doc.filename,
                    "document_type": doc.document_type,
                    "status": doc.status,
                    "confidence": _confidence_band(item.score),
                    "highlights": item.highlights,
                    "metadata": doc.metadata_,
                }
            )

        # F80.5: cross-encoder rerank the merged top-K into top-limit.
        # Uses the top-1 highlight per doc as the cross-encoder input —
        # chunk-level is the natural unit since 512-token limit forbids
        # whole-doc reranking anyway.
        if self._reranker is not None and results:
            results = self._rerank_results(query, results, limit)
        else:
            results = results[:limit]

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return results, elapsed_ms

    async def retrieve_chunks(
        self,
        *,
        actor: User,
        query: str,
        document_ids: list[UUID] | None,
        limit: int,
    ) -> list[RetrievedChunk]:
        """F81.k — chunk-level hybrid retrieval for RAG.

        Runs the same vector + FTS (+ trigram fallback) pipeline as
        ``search()`` but keeps chunks as the unit of output.

        F89.a — when the ``QueryParser`` extracts structured filters
        from the query ("5+ years Python"), the SQL metadata path
        activates and its matching document set HARD-filters the
        vector/lexical hits. Pure-semantic queries (empty parsed
        filters) skip this path, preserving the F81.k default of
        "no SQL path for RAG." The intersection semantics
        (not boost) reflect user intent: a year-threshold is
        exclusionary, not a hint.

        Ownership is enforced at retrieval — HR users only see their
        own chunks, admins bypass.
        """
        if not query.strip():
            return []

        # F89.a — parse the query before hitting any retrieval source.
        # Empty filters = pure-semantic query = unchanged F81.k behavior.
        parsed = self._query_parser.parse(query)

        owner_filter = None if actor.role == UserRole.ADMIN else actor.id

        # Vector path — reuse the private helper that handles
        # embedder selection, distance filtering, and the where clause.
        vector_hits = self._vector_search(query, None, limit * 3, owner_id=owner_filter)
        vector_hits = await self._drop_orphan_vector_hits(vector_hits)

        # Lexical path — F88 acronym + typo + tech-token preservation.
        lexical_query = expand_acronyms(normalize_tech_tokens(query))
        lexical_hits = await self._documents.full_text_search(
            lexical_query, limit=limit * 3, owner_id=owner_filter
        )
        if not lexical_hits:
            lexical_hits = await self._documents.fuzzy_search(
                query, limit=limit * 3, owner_id=owner_filter
            )

        # F89.a — hard-filter by parsed structured filters before
        # merging. "5+ years Python" means a candidate with 2 years
        # Python must not surface; intersection semantics enforce
        # that. Only runs when a STRONG filter is present — a
        # standalone skill mention ("what is Python used for") is
        # ambiguous and preserves the pure-semantic F81.k default.
        if parsed.filters.has_strong_filter:
            parsed_doctype = (
                _document_type_from_str(parsed.filters.document_type)
                if parsed.filters.document_type
                else None
            )
            sql_docs = await self._documents.search_by_metadata(
                document_type=parsed_doctype,
                skills=list(parsed.filters.skills) or None,
                min_experience_years=parsed.filters.min_experience_years,
                date_from=parsed.filters.date_from,
                date_to=parsed.filters.date_to,
                limit=limit * 3,
                owner_id=owner_filter,
            )
            sql_doc_ids = {doc.id for doc in sql_docs}
            vector_hits = [
                h for h in vector_hits if _safe_uuid(h.document_id) in sql_doc_ids
            ]
            lexical_hits = [(d, s) for d, s in lexical_hits if d.id in sql_doc_ids]

        merge_limit = max(settings.reranker_top_k, limit) if self._reranker else limit
        merged = self._rrf_merge_chunks(
            vector_hits,
            lexical_hits,
            merge_limit,
            w_vector=settings.rrf_weight_vector,
            w_lexical=settings.rrf_weight_lexical,
        )

        # Post-filter by document_ids if set. Pushdown to FTS/SQL
        # would require widening DocumentRepository signatures;
        # scope-fenced as a follow-up (F81.k followups).
        if document_ids:
            requested = set(document_ids)
            merged = [c for c in merged if c.document_id in requested]

        # Hydrate filenames and drop non-READY docs in one pass.
        doc_ids = list({c.document_id for c in merged})
        docs_map = await self._documents.get_many(doc_ids)
        hydrated: list[RetrievedChunk] = []
        for chunk in merged:
            doc = docs_map.get(chunk.document_id)
            if doc is None or doc.status != DocumentStatus.READY:
                continue
            hydrated.append(replace(chunk, filename=doc.filename))

        if self._reranker is not None and hydrated:
            return self._rerank_chunks(query, hydrated, limit)
        return hydrated[:limit]

    async def find_similar_documents(
        self,
        *,
        actor: User,
        source_document_id: UUID,
        limit: int = 10,
    ) -> list[SimilarDocument]:
        """F89.c — find documents most similar to ``source_document_id``.

        Semantic similarity is measured between mean-pooled chunk-
        embedding centroids per document. The source document is
        excluded from results. HR users are scoped to their own docs;
        admins see across owners.

        Raises ``ServiceUnavailable`` when the similarity store isn't
        wired, ``NotFound`` when the source doc doesn't exist,
        ``Forbidden`` when the actor can't access the source,
        ``DocumentNotIndexed`` when the source has no doc-level vector
        (caller should advise re-index).
        """
        if self._similarity_store is None:
            raise ServiceUnavailable(
                "Similarity search is not available on this deployment."
            )

        source = await self._documents.get(source_document_id)
        if source is None:
            raise NotFound("Document not found.")
        if actor.role != UserRole.ADMIN and source.owner_id != actor.id:
            raise Forbidden("You do not have access to this document.")
        if source.status != DocumentStatus.READY:
            # A non-READY source doc has no usable vector; behave the
            # same as "not found" from the caller's POV — don't leak
            # the status distinction across the ownership boundary.
            raise NotFound("Document not found.")

        where: dict[str, Any] | None = None
        if actor.role != UserRole.ADMIN:
            where = {"owner_id": str(actor.id)}

        # Over-fetch by one so we can drop the source's self-match
        # without shrinking the user-visible result set. HNSW's
        # approximate recall can occasionally miss the source entirely,
        # so we always filter-then-truncate rather than assume index 0.
        hits = self._similarity_store.find_similar_documents(
            str(source_document_id),
            n_results=limit + 1,
            where=where,
        )

        # Drop the source document from the neighbour set.
        neighbour_ids: list[UUID] = []
        distances: dict[UUID, float] = {}
        for hit in hits:
            doc_uuid = _safe_uuid(hit.document_id)
            if doc_uuid is None or doc_uuid == source_document_id:
                continue
            neighbour_ids.append(doc_uuid)
            distances[doc_uuid] = hit.distance

        if not neighbour_ids:
            return []

        docs_map = await self._documents.get_many(neighbour_ids)

        results: list[SimilarDocument] = []
        for doc_id in neighbour_ids:
            doc = docs_map.get(doc_id)
            if doc is None or doc.status != DocumentStatus.READY:
                # Drift safety — parallel of the F86.c chunk-path check.
                continue
            # Defence-in-depth owner filter. Chroma's ``where`` already
            # enforces scoping, but a stale metadata row (e.g. doc
            # reassigned) must never be the thing that breaks tenant
            # isolation. Same belt-and-braces shape used by search.
            if actor.role != UserRole.ADMIN and doc.owner_id != actor.id:
                continue
            distance = distances[doc_id]
            results.append(
                SimilarDocument(
                    document_id=doc.id,
                    filename=doc.filename,
                    document_type=doc.document_type,
                    similarity=max(0.0, 1.0 - distance),
                    metadata=doc.metadata_ or {},
                )
            )
            if len(results) >= limit:
                break
        return results

    def _rerank_chunks(
        self, query: str, chunks: list[RetrievedChunk], limit: int
    ) -> list[RetrievedChunk]:
        """Apply the cross-encoder reranker at chunk granularity.

        Metadata on ``RerankCandidate`` carries the chunk_index so we
        can match the reordered candidates back to the original chunk
        records — ``document_id`` alone isn't unique when a doc
        contributes multiple chunks.
        """
        candidates = [
            RerankCandidate(
                document_id=c.document_id,
                text=c.text,
                original_score=c.score,
                metadata={"chunk_index": c.chunk_index},
            )
            for c in chunks
        ]
        try:
            reranked = self._reranker.rerank(query, candidates, top_n=limit)
        except Exception:
            logger.exception("chunk rerank failed; falling back to RRF order")
            return chunks[:limit]

        by_key = {(c.document_id, c.chunk_index): c for c in chunks}
        result: list[RetrievedChunk] = []
        for cand in reranked:
            chunk_index = cand.metadata.get("chunk_index", 0)
            chunk = by_key.get((cand.document_id, chunk_index))
            if chunk is not None:
                result.append(chunk)
        return result

    @staticmethod
    def _rrf_merge_chunks(
        vector_hits: list[VectorHit],
        lexical_hits: list[tuple[Document, float]],
        limit: int,
        *,
        w_vector: float,
        w_lexical: float,
    ) -> list[RetrievedChunk]:
        """Chunk-level RRF for RAG retrieval.

        Vector hits are chunks → each gets its own rank contribution.
        Lexical hits are doc-level → they boost every vector-retrieved
        chunk from the matching doc but never fabricate chunks for
        docs where vector found nothing. Keeps the LLM's context
        grounded in chunks we actually have text for.
        """
        chunk_scores: dict[tuple[UUID, int], float] = defaultdict(float)
        chunk_data: dict[tuple[UUID, int], VectorHit] = {}

        for rank, hit in enumerate(vector_hits):
            try:
                doc_id = UUID(hit.document_id)
            except ValueError:
                continue
            chunk_index = hit.metadata.get("chunk_index", 0)
            key = (doc_id, chunk_index)
            chunk_scores[key] += w_vector / (_RRF_K + rank + 1)
            chunk_data[key] = hit

        for rank, (doc, _score) in enumerate(lexical_hits):
            doc_boost = w_lexical / (_RRF_K + rank + 1)
            for key in chunk_scores:
                if key[0] == doc.id:
                    chunk_scores[key] += doc_boost

        sorted_keys = sorted(chunk_scores, key=lambda k: chunk_scores[k], reverse=True)
        return [
            RetrievedChunk(
                document_id=key[0],
                filename="",  # hydrated by caller
                chunk_index=key[1],
                text=chunk_data[key].text,
                distance=chunk_data[key].distance,
                score=chunk_scores[key],
                metadata=chunk_data[key].metadata,
            )
            for key in sorted_keys[:limit]
        ]

    def _rerank_results(
        self, query: str, results: list[dict[str, Any]], limit: int
    ) -> list[dict[str, Any]]:
        """Apply the cross-encoder reranker; fall back to RRF order on failure."""
        candidates = [
            RerankCandidate(
                document_id=r["document_id"],
                text=(r["highlights"][0]["text"] if r["highlights"] else r["filename"]),
                original_score=0.0,
            )
            for r in results
        ]
        try:
            reranked = self._reranker.rerank(query, candidates, top_n=limit)
        except Exception:
            logger.exception("rerank failed; falling back to RRF order")
            return results[:limit]

        by_id = {r["document_id"]: r for r in results}
        return [by_id[c.document_id] for c in reranked if c.document_id in by_id]

    async def _drop_orphan_vector_hits(self, hits: list[VectorHit]) -> list[VectorHit]:
        """Drop vector hits whose document is missing or non-READY in Postgres.

        Chroma is the source of truth for chunks, Postgres for documents.
        Drift between them (deleted docs, failed reprocessing) leaves
        chunks pointing at nonexistent rows. Without this filter those
        orphans collect RRF score and shadow real lexical hits.
        """
        if not hits:
            return hits
        doc_ids: list[UUID] = []
        for h in hits:
            try:
                doc_ids.append(UUID(h.document_id))
            except ValueError:
                continue
        if not doc_ids:
            return []
        existing = await self._documents.get_many(doc_ids)
        return [
            h
            for h in hits
            if (
                (doc_id := _safe_uuid(h.document_id)) is not None
                and (existing.get(doc_id))
                and existing[doc_id].status == DocumentStatus.READY
            )
        ]

    def _vector_search(
        self,
        query: str,
        document_type: DocumentType | None,
        n_results: int,
        *,
        owner_id: UUID | None = None,
    ) -> list[VectorHit]:
        if self._vector_store is None:
            return []

        clauses: list[dict[str, Any]] = []
        if document_type is not None:
            clauses.append({"document_type": document_type.value})
        if owner_id is not None:
            clauses.append({"owner_id": str(owner_id)})

        # Chroma `where` accepts a single condition as a flat dict but
        # requires an explicit `$and` for multi-condition composition.
        where: dict[str, Any] | None
        if not clauses:
            where = None
        elif len(clauses) == 1:
            where = clauses[0]
        else:
            where = {"$and": clauses}

        hits = self._vector_store.query(
            query_text=query, n_results=n_results, where=where
        )
        # Drop hits worse than the cosine-distance ceiling. Keeping them
        # means ChromaDB's "top N" becomes "everything matches" as soon
        # as the inbox is mostly irrelevant to the query.
        #
        # F85.d: threshold resolution order —
        # 1) explicit ``settings.search_max_distance`` override
        # 2) embedder's per-model recommendation
        # 3) safe default (0.5)
        threshold = self._resolve_distance_threshold()
        return [h for h in hits if h.distance <= threshold]

    def _resolve_distance_threshold(self) -> float:
        if settings.search_max_distance is not None:
            return settings.search_max_distance
        embedder = getattr(self._vector_store, "embedder", None)
        if embedder is not None:
            return embedder.recommended_distance_threshold
        return 0.5

    @staticmethod
    def _rrf_merge(
        vector_hits: list[VectorHit],
        sql_docs: list[Document],
        lexical_hits: list[tuple[Document, float]],
        limit: int,
        *,
        w_vector: float = 1.0,
        w_sql: float = 1.0,
        w_lexical: float = 1.0,
    ) -> list[SearchResult]:
        """Weighted Reciprocal Rank Fusion across the three retrieval sources.

        Per-source ``ts_rank_cd`` and cosine distance scores aren't on the
        same axis; we collapse to ranks and let RRF do the merging. The
        ``w_*`` multipliers (F85.c) let the caller bias sources without
        normalizing scores — e.g. ``w_lexical=2.0`` gives filename/
        metadata matches from F87's weighted tsvector a bigger say in the
        final ordering. Defaults of 1.0 keep classical equal-weight RRF.
        """
        scores: dict[UUID, float] = defaultdict(float)
        highlights_by_doc: dict[UUID, list[dict[str, Any]]] = defaultdict(list)

        for rank, hit in enumerate(vector_hits):
            try:
                doc_id = UUID(hit.document_id)
            except ValueError:
                continue
            scores[doc_id] += w_vector / (_RRF_K + rank + 1)
            highlights_by_doc[doc_id].append(
                {
                    "text": hit.text,
                    "chunk_index": hit.metadata.get("chunk_index", 0),
                }
            )

        for rank, doc in enumerate(sql_docs):
            scores[doc.id] += w_sql / (_RRF_K + rank + 1)

        for rank, (doc, _ts_score) in enumerate(lexical_hits):
            scores[doc.id] += w_lexical / (_RRF_K + rank + 1)

        sorted_ids = sorted(scores, key=lambda did: scores[did], reverse=True)

        cap = settings.search_max_highlights_per_doc
        results: list[SearchResult] = []
        for doc_id in sorted_ids[:limit]:
            deduped: list[dict[str, Any]] = []
            seen_chunks: set[int] = set()
            for h in highlights_by_doc.get(doc_id, []):
                if h["chunk_index"] in seen_chunks:
                    continue
                seen_chunks.add(h["chunk_index"])
                deduped.append(h)
                if len(deduped) >= cap:
                    break

            results.append(
                SearchResult(
                    document_id=doc_id,
                    score=scores[doc_id],  # raw — no normalization lie
                    highlights=deduped,
                )
            )

        return results


def _safe_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _document_type_from_str(value: str) -> DocumentType | None:
    """F89.a — convert a parsed document-type string to the enum.

    ``QueryParser`` emits strings (to avoid import-cycling the enum
    into ``adapters/protocols.py``); ``SearchService`` converts at
    the boundary. Unknown values fall back to None rather than
    raising — a malformed parser output shouldn't 500 the request.
    """
    try:
        return DocumentType(value)
    except ValueError:
        return None


def _confidence_band(score: float) -> Confidence:
    if score >= settings.search_confidence_high:
        return "high"
    if score >= settings.search_confidence_medium:
        return "medium"
    return "low"
