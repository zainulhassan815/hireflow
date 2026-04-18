"""Hybrid search: vector similarity + metadata filtering with RRF merge.

F80 made the previously permissive scoring honest:

* Vector hits above ``search_max_distance`` are discarded before
  ranking (stops "every query returns everything").
* The SQL metadata path only contributes when structured filters are
  present (no more "recent documents for any query").
* Raw RRF scores are not normalized up to 1.0 — an absolute
  confidence band (``high`` / ``medium`` / ``low``) rides in the
  response instead.
* Highlights per document are deduped and capped so one multi-chunk
  resume doesn't dominate the result card.
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
from app.models import Document, DocumentType
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
        query: str,
        document_type: DocumentType | None = None,
        skills: list[str] | None = None,
        min_experience_years: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 10,
    ) -> tuple[list[dict[str, Any]], int]:
        """Run hybrid search. Returns (results, query_time_ms)."""
        start = time.monotonic()

        vector_hits = self._vector_search(query, document_type, limit * 3)

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
            )
        else:
            sql_docs = []

        merged = self._rrf_merge(vector_hits, sql_docs, limit)

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
    ) -> list[VectorHit]:
        if self._vector_store is None:
            return []

        where: dict[str, Any] | None = None
        if document_type is not None:
            where = {"document_type": document_type.value}

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
        limit: int,
    ) -> list[SearchResult]:
        """Reciprocal Rank Fusion across vector and SQL result lists."""
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
