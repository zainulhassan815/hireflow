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

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from app.adapters.protocols import VectorHit, VectorStore
from app.core.config import settings
from app.models import Document, DocumentType, User, UserRole
from app.repositories.document import DocumentRepository
from app.services.highlight import extract_query_terms, find_match_spans

_RRF_K = 60  # standard reciprocal rank fusion constant

Confidence = Literal["high", "medium", "low"]


@dataclass
class SearchResult:
    document_id: UUID
    score: float
    highlights: list[dict[str, Any]] = field(default_factory=list)


class SearchService:
    def __init__(
        self,
        documents: DocumentRepository,
        vector_store: VectorStore | None,
    ) -> None:
        self._documents = documents
        self._vector_store = vector_store

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

        owner_filter = None if actor.role == UserRole.ADMIN else actor.id

        vector_hits = self._vector_search(
            query, document_type, limit * 3, owner_id=owner_filter
        )

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

        lexical_hits = await self._documents.full_text_search(
            query, limit=limit * 3, owner_id=owner_filter
        )

        merged = self._rrf_merge(vector_hits, sql_docs, lexical_hits, limit)

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

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return results, elapsed_ms

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
        # Drop hits worse than the configured cosine-distance ceiling.
        # Keeping them means ChromaDB's "top N" becomes "everything
        # matches" as soon as the inbox is mostly irrelevant to the
        # query.
        return [h for h in hits if h.distance <= settings.search_max_distance]

    @staticmethod
    def _rrf_merge(
        vector_hits: list[VectorHit],
        sql_docs: list[Document],
        lexical_hits: list[tuple[Document, float]],
        limit: int,
    ) -> list[SearchResult]:
        """Reciprocal Rank Fusion across vector, SQL-metadata, and lexical lists.

        Equal-weight RRF: the per-source ``ts_rank_cd`` and cosine distance
        scores are not comparable on the same axis, so we collapse to ranks
        and let RRF do the merging. A doc that surfaces in two sources
        outranks one that appears in only one.
        """
        scores: dict[UUID, float] = defaultdict(float)
        highlights_by_doc: dict[UUID, list[dict[str, Any]]] = defaultdict(list)

        for rank, hit in enumerate(vector_hits):
            try:
                doc_id = UUID(hit.document_id)
            except ValueError:
                continue
            scores[doc_id] += 1.0 / (_RRF_K + rank + 1)
            highlights_by_doc[doc_id].append(
                {
                    "text": hit.text,
                    "chunk_index": hit.metadata.get("chunk_index", 0),
                }
            )

        for rank, doc in enumerate(sql_docs):
            scores[doc.id] += 1.0 / (_RRF_K + rank + 1)

        for rank, (doc, _ts_score) in enumerate(lexical_hits):
            scores[doc.id] += 1.0 / (_RRF_K + rank + 1)

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


def _confidence_band(score: float) -> Confidence:
    if score >= settings.search_confidence_high:
        return "high"
    if score >= settings.search_confidence_medium:
        return "medium"
    return "low"
