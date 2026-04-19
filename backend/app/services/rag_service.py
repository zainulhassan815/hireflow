"""RAG: retrieve context chunks, build prompt, generate answer with citations."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.adapters.protocols import ChunkRetriever, LlmProvider, RetrievedChunk
from app.core.config import settings
from app.domain.exceptions import LlmProviderError
from app.models import User
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

# F81.c — token estimator. Anthropic publishes "~4 chars per token" as
# a rule of thumb for Claude. It's approximate on every model; we use
# it only for budget soft-capping, never for hard LLM-API limit checks.
# Ceil-divide so a 5-char string counts as 2 tokens, not 1 (conservative
# — better to under-pack than to overflow). Promoted to a shared module
# if a second caller appears; today there's one.
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Approximate token count for budget accounting."""
    return (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN


# F81.e — user-visible confidence band for the answer.
Confidence = Literal["high", "medium", "low"]


def _compute_confidence(kept: list[RetrievedChunk]) -> Confidence:
    """Derive the confidence band from the chunks the LLM will see.

    Today: top-chunk distance only. The signature takes the full list
    so future signals (distance spread, reranker-score gap,
    ``len(kept)``) slot in without a caller rewrite. ``kept`` must be
    non-empty by construction — callers short-circuit to the no-hits
    sentinel before computing confidence.
    """
    top = kept[0].distance
    if top <= settings.rag_confidence_high_max_distance:
        return "high"
    if top <= settings.rag_confidence_medium_max_distance:
        return "medium"
    return "low"


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
    confidence: Confidence | None = None


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
    confidence: Confidence


class RagService:
    def __init__(
        self,
        retriever: ChunkRetriever,
        llm: LlmProvider,
    ) -> None:
        self._retriever = retriever
        self._llm = llm

    async def query(
        self,
        *,
        actor: User,
        question: str,
        document_ids: list[UUID] | None = None,
        max_chunks: int = 5,
    ) -> RagResult:
        start = time.monotonic()
        ctx = await self._build_context(
            actor=actor,
            question=question,
            document_ids=document_ids,
            max_chunks=max_chunks,
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
            confidence=ctx.confidence,
        )

    async def stream_query(
        self,
        *,
        actor: User,
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
            actor=actor,
            question=question,
            document_ids=document_ids,
            max_chunks=max_chunks,
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
        except LlmProviderError as exc:
            # Known provider failure — adapter already translated from
            # SDK types to our domain taxonomy. WARN without a stack
            # trace: rate-limits and transient outages are expected
            # operational events, not bugs.
            logger.warning("LLM provider error (%s): %s", exc.code, exc)
            yield ErrorEvent(
                data=ErrorBody(
                    code=exc.code,
                    message=str(exc),
                    details=exc.details(),
                ),
            )
            return
        except Exception:
            # Genuinely unknown failure — full traceback so operators
            # can diagnose and add a translation if the pattern
            # repeats. Client sees a generic message.
            logger.exception("Unexpected LLM stream failure")
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
                confidence=ctx.confidence,
            )
        )

    async def _build_context(
        self,
        *,
        actor: User,
        question: str,
        document_ids: list[UUID] | None,
        max_chunks: int,
    ) -> _RagContext | None:
        """Retrieve chunks via ChunkRetriever, build prompt + citations.

        F81.k — retrieval now goes through ``ChunkRetriever`` (owned
        by ``SearchService``), inheriting F85.c weighted RRF over
        vector + lexical hits, F88 acronym/typo tolerance, and F80.5
        cross-encoder reranking. RagService applies its own tighter
        gates on top (F81.b distance cutoff, F81.c token budget).

        Returns ``None`` if retrieval produced no usable chunks — the
        no-hits sentinel path in callers handles the fallback.
        """
        chunks = await self._retriever.retrieve_chunks(
            actor=actor,
            query=question,
            document_ids=document_ids,
            limit=max_chunks,
        )
        if not chunks:
            return None

        cutoff = settings.rag_context_max_distance
        budget = settings.rag_context_token_budget
        kept, tokens_used = self._apply_context_gate(chunks, cutoff, budget)
        logger.info(
            "rag context: %d/%d chunks kept, ~%d tokens (cutoff=%s, budget=%d)",
            len(kept),
            len(chunks),
            tokens_used,
            "none" if cutoff is None else f"{cutoff:.2f}",
            budget,
        )
        if not kept:
            return None

        context_parts: list[str] = []
        citations: list[dict[str, Any]] = []
        terms = extract_query_terms(question)

        for chunk in kept:
            context_parts.append(
                _CONTEXT_TEMPLATE.format(
                    filename=chunk.filename,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                )
            )
            snippet = chunk.text[:500]
            citations.append(
                {
                    "document_id": chunk.document_id,
                    "filename": chunk.filename,
                    "chunk_index": chunk.chunk_index,
                    "text": snippet,
                    "match_spans": find_match_spans(snippet, terms),
                    # F81.h — surface chunker metadata so the frontend
                    # can render "filename · section · p.N" without
                    # another round-trip. Missing keys return None.
                    "section_heading": chunk.metadata.get("section_heading"),
                    "page_number": chunk.metadata.get("page_number"),
                }
            )

        context = "\n".join(context_parts)
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"
        return _RagContext(
            citations=citations,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            confidence=_compute_confidence(kept),
        )

    @staticmethod
    def _apply_context_gate(
        chunks: list[RetrievedChunk], cutoff: float | None, budget: int
    ) -> tuple[list[RetrievedChunk], int]:
        """Apply F81.b distance filter + F81.c token budget.

        Returns ``(kept, tokens_used)``. Walks ``chunks`` in retrieval
        order (already ranked best-first by the retriever).

        F81.b cutoff is a tightening knob: when ``None``, retrieve_chunks
        already filtered at the search distance threshold, so no
        double-filter is needed. An explicit float re-filters tighter.

        A single chunk whose own estimated tokens exceed the entire
        budget is kept anyway with a WARN log — preserves answer
        capability in the face of chunking pathologies; the LLM may
        error, in which case ``stream_query``'s existing handler
        converts it to an ``error`` event.
        """
        kept: list[RetrievedChunk] = []
        tokens_used = 0
        for chunk in chunks:
            if cutoff is not None and chunk.distance > cutoff:
                continue
            chunk_tokens = _estimate_tokens(chunk.text)
            if not kept and chunk_tokens > budget:
                logger.warning(
                    "rag context: top chunk ~%d tokens exceeds budget %d; "
                    "keeping it to preserve answer capability",
                    chunk_tokens,
                    budget,
                )
                return [chunk], chunk_tokens
            if tokens_used + chunk_tokens > budget:
                break
            kept.append(chunk)
            tokens_used += chunk_tokens
        return kept, tokens_used
