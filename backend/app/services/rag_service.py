"""RAG: retrieve context chunks, build prompt, generate answer with citations."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.adapters.protocols import LlmProvider, VectorStore
from app.repositories.document import DocumentRepository
from app.schemas.errors import ErrorBody
from app.schemas.rag import (
    CitationsEvent,
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    SourceCitation,
    StreamDone,
)
from app.services.highlight import extract_query_terms, find_match_spans

logger = logging.getLogger(__name__)

# F81.d — tighter system prompt. Rules over prose.
#
# Each rule exists for a reason:
#   1. Hard "I don't know" contract — the assistant returns an exact
#      sentinel string so the frontend (and downstream consumers) can
#      detect zero-knowledge answers without heuristic matching.
#   2. Inline filename citation — makes claims verifiable at a glance
#      and pairs with the F82.e section_heading metadata that already
#      travels on each chunk.
#   3. No preamble — removes the "Based on the documents…" boilerplate
#      that wastes tokens and burns reader attention.
#   4. Format hints — bullets for enumerations, tables for comparisons,
#      so answers are shaped right for the question.
#   5. Length cap — stops the model from padding.
_SYSTEM_PROMPT = """\
You are an HR document-search assistant. Answer questions using only the
provided document context.

Rules:
1. If the context does not contain the answer, respond with exactly:
   Not in the provided documents.
   Do not guess, do not speculate, do not offer adjacent information.
2. Cite the source filename inline, in square brackets, for every
   specific claim — e.g. "Alice has 5 years of Kubernetes experience
   [alice_resume.pdf]." One citation per claim; do not stack multiple
   filenames on the same claim.
3. Be direct. Do not open with phrases like "Based on the documents",
   "According to the provided context", or "The documents state".
   Start with the answer itself.
4. Use bullet points when listing three or more items. Use a markdown
   table only when comparing the same attribute across two or more
   documents (e.g. years of experience across three candidates).
5. Keep the answer under 200 words unless a table or list is warranted.
"""

_CONTEXT_TEMPLATE = """\
--- Document: {filename} (chunk {chunk_index}) ---
{text}
"""

_FALLBACK_NO_HITS = "Not in the provided documents."


@dataclass
class RagResult:
    answer: str
    citations: list[dict[str, Any]]
    model: str
    query_time_ms: int


@dataclass
class _RagContext:
    """Shared output of the retrieval + prompt-assembly stage.

    Both ``query`` and ``stream_query`` consume one of these so
    retrieval behaviour stays identical across the sync and streaming
    paths. ``None`` is returned instead when retrieval produced zero
    hits — callers handle the fallback uniformly.
    """

    citations: list[dict[str, Any]]
    system_prompt: str
    user_prompt: str


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
        ctx = await self._build_context(
            question=question, document_ids=document_ids, max_chunks=max_chunks
        )
        if ctx is None:
            return RagResult(
                answer=_FALLBACK_NO_HITS,
                citations=[],
                model=self._llm.model_name,
                query_time_ms=int((time.monotonic() - start) * 1000),
            )

        answer = await asyncio.to_thread(
            self._llm.complete, ctx.system_prompt, ctx.user_prompt
        )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "RAG query answered in %dms using %d chunks",
            elapsed_ms,
            len(ctx.citations),
        )
        return RagResult(
            answer=answer,
            citations=ctx.citations,
            model=self._llm.model_name,
            query_time_ms=elapsed_ms,
        )

    async def stream_query(
        self,
        *,
        question: str,
        document_ids: list[UUID] | None = None,
        max_chunks: int = 5,
    ) -> AsyncIterator[CitationsEvent | DeltaEvent | DoneEvent | ErrorEvent]:
        """Yield SSE events for a single RAG query.

        Event sequence:
          - ``citations`` once (omitted when there are no hits)
          - ``delta`` 0..N times
          - ``done`` once on success, or ``error`` once on failure
        """
        start = time.monotonic()
        ctx = await self._build_context(
            question=question, document_ids=document_ids, max_chunks=max_chunks
        )

        if ctx is None:
            # Fallback path: no hits. Emit a single synthetic delta so
            # the UI can render the sentinel as normal assistant text,
            # then close with ``done``. Keeping this consistent with the
            # sync ``query`` fallback means downstream consumers don't
            # branch on "was it retrieval-empty".
            yield DeltaEvent(data=_FALLBACK_NO_HITS)
            yield DoneEvent(
                data=StreamDone(
                    model=self._llm.model_name,
                    query_time_ms=int((time.monotonic() - start) * 1000),
                )
            )
            return

        yield CitationsEvent(
            data=[SourceCitation(**c) for c in ctx.citations],
        )

        try:
            async for chunk in self._llm.stream(ctx.system_prompt, ctx.user_prompt):
                yield DeltaEvent(data=chunk)
        except Exception:
            # Full traceback + exception detail goes to the server log.
            # The client-visible ``ErrorBody.message`` is documented as
            # "safe to display to end users" (see schemas/errors.py),
            # so we deliberately do not surface ``str(exc)`` — raw SDK
            # error strings can contain internal URLs, request IDs, or
            # partial credentials.
            logger.exception("LLM stream failed")
            yield ErrorEvent(
                data=ErrorBody(
                    code="llm_error",
                    message=(
                        "The AI provider failed while generating this "
                        "answer. Please try again in a moment."
                    ),
                ),
            )
            return

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "RAG stream completed in %dms using %d chunks",
            elapsed_ms,
            len(ctx.citations),
        )
        yield DoneEvent(
            data=StreamDone(
                model=self._llm.model_name,
                query_time_ms=elapsed_ms,
            )
        )

    async def _build_context(
        self,
        *,
        question: str,
        document_ids: list[UUID] | None,
        max_chunks: int,
    ) -> _RagContext | None:
        """Retrieve chunks, hydrate filenames, build prompt + citations.

        Returns ``None`` if retrieval produced no hits. Otherwise
        returns everything both ``query`` and ``stream_query`` need to
        call the LLM.
        """
        where = self._build_where(document_ids)
        hits = self._vector_store.query(
            query_text=question, n_results=max_chunks, where=where
        )
        if not hits:
            return None

        doc_ids = list({UUID(h.document_id) for h in hits})
        docs_map = await self._documents.get_many(doc_ids)

        context_parts: list[str] = []
        citations: list[dict[str, Any]] = []
        terms = extract_query_terms(question)

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
            snippet = hit.text[:500]
            citations.append(
                {
                    "document_id": doc_id,
                    "filename": filename,
                    "chunk_index": chunk_index,
                    "text": snippet,
                    "match_spans": find_match_spans(snippet, terms),
                }
            )

        context = "\n".join(context_parts)
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"
        return _RagContext(
            citations=citations,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

    @staticmethod
    def _build_where(document_ids: list[UUID] | None) -> dict[str, Any] | None:
        if not document_ids:
            return None
        if len(document_ids) == 1:
            return {"document_id": str(document_ids[0])}
        return {"document_id": {"$in": [str(d) for d in document_ids]}}
