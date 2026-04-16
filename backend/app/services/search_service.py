"""Hybrid search: vector similarity + metadata filtering with RRF merge."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.adapters.protocols import VectorHit, VectorStore
from app.models import Document, DocumentType
from app.repositories.document import DocumentRepository

_RRF_K = 60  # standard reciprocal rank fusion constant


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

        # 1. Vector search
        vector_hits = self._vector_search(query, document_type, limit * 3)

        # 2. SQL metadata search
        sql_docs = await self._documents.search_by_metadata(
            document_type=document_type,
            skills=skills,
            min_experience_years=min_experience_years,
            date_from=date_from,
            date_to=date_to,
            limit=limit * 3,
        )

        # 3. Reciprocal Rank Fusion
        merged = self._rrf_merge(vector_hits, sql_docs, limit)

        # 4. Hydrate with full document data
        doc_ids = [m.document_id for m in merged]
        docs_map = await self._documents.get_many(doc_ids)

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
                    "score": round(item.score, 4),
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

        return self._vector_store.query(
            query_text=query, n_results=n_results, where=where
        )

    @staticmethod
    def _rrf_merge(
        vector_hits: list[VectorHit],
        sql_docs: list[Document],
        limit: int,
    ) -> list[SearchResult]:
        """Reciprocal Rank Fusion across vector and SQL result lists."""
        scores: dict[UUID, float] = defaultdict(float)
        highlights: dict[UUID, list[dict[str, Any]]] = defaultdict(list)

        # Score vector hits
        for rank, hit in enumerate(vector_hits):
            try:
                doc_id = UUID(hit.document_id)
            except ValueError:
                continue
            scores[doc_id] += 1.0 / (_RRF_K + rank + 1)
            highlights[doc_id].append(
                {
                    "text": hit.text,
                    "chunk_index": hit.metadata.get("chunk_index", 0),
                }
            )

        # Score SQL results
        for rank, doc in enumerate(sql_docs):
            scores[doc.id] += 1.0 / (_RRF_K + rank + 1)

        # Sort by fused score descending
        sorted_ids = sorted(scores, key=lambda did: scores[did], reverse=True)

        # Normalize scores to 0–1
        max_score = scores[sorted_ids[0]] if sorted_ids else 1.0

        results = []
        for doc_id in sorted_ids[:limit]:
            results.append(
                SearchResult(
                    document_id=doc_id,
                    score=scores[doc_id] / max_score if max_score > 0 else 0,
                    highlights=highlights.get(doc_id, []),
                )
            )

        return results
