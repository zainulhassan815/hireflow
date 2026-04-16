"""RAG: retrieve context chunks, build prompt, generate answer with citations."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.adapters.protocols import LlmProvider, VectorStore
from app.repositories.document import DocumentRepository

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an AI assistant for an HR document management system.
Answer the user's question using ONLY the provided document context.
If the context doesn't contain enough information, say so honestly.
Do not make up information that isn't in the context.

When referencing information, mention which document it comes from
(use the filename). Be concise and direct."""

_CONTEXT_TEMPLATE = """\
--- Document: {filename} (chunk {chunk_index}) ---
{text}
"""


@dataclass
class RagResult:
    answer: str
    citations: list[dict[str, Any]]
    model: str
    query_time_ms: int


class RagService:
    def __init__(
        self,
        documents: DocumentRepository,
        vector_store: VectorStore,
        llm: LlmProvider,
    ) -> None:
        self._documents = documents
        self._vector_store = vector_store
        self._llm = llm

    async def query(
        self,
        *,
        question: str,
        document_ids: list[UUID] | None = None,
        max_chunks: int = 5,
    ) -> RagResult:
        start = time.monotonic()

        # 1. Retrieve relevant chunks
        where = self._build_where(document_ids)
        hits = self._vector_store.query(
            query_text=question, n_results=max_chunks, where=where
        )

        if not hits:
            return RagResult(
                answer="I couldn't find any relevant information in the uploaded documents.",
                citations=[],
                model=self._llm.model_name,
                query_time_ms=int((time.monotonic() - start) * 1000),
            )

        # 2. Hydrate with document metadata for filenames
        doc_ids = list({UUID(h.document_id) for h in hits})
        docs_map = await self._documents.get_many(doc_ids)

        # 3. Build context + citations
        context_parts: list[str] = []
        citations: list[dict[str, Any]] = []

        for hit in hits:
            doc_id = UUID(hit.document_id)
            doc = docs_map.get(doc_id)
            filename = doc.filename if doc else "unknown"
            chunk_index = hit.metadata.get("chunk_index", 0)

            context_parts.append(
                _CONTEXT_TEMPLATE.format(
                    filename=filename,
                    chunk_index=chunk_index,
                    text=hit.text,
                )
            )
            citations.append(
                {
                    "document_id": doc_id,
                    "filename": filename,
                    "chunk_index": chunk_index,
                    "text": hit.text[:500],
                }
            )

        context = "\n".join(context_parts)
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

        # 4. Call LLM (sync → run in thread)
        answer = await asyncio.to_thread(
            self._llm.complete, _SYSTEM_PROMPT, user_prompt
        )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "RAG query answered in %dms using %d chunks from %d documents",
            elapsed_ms,
            len(hits),
            len(doc_ids),
        )

        return RagResult(
            answer=answer,
            citations=citations,
            model=self._llm.model_name,
            query_time_ms=elapsed_ms,
        )

    @staticmethod
    def _build_where(document_ids: list[UUID] | None) -> dict[str, Any] | None:
        if not document_ids:
            return None
        if len(document_ids) == 1:
            return {"document_id": str(document_ids[0])}
        return {"document_id": {"$in": [str(d) for d in document_ids]}}
