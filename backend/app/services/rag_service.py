"""RAG: retrieve context chunks, build prompt, generate answer with citations."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.adapters.protocols import (
    ChunkRetriever,
    IntentClassifier,
    LlmProvider,
    RetrievedChunk,
)
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
from app.services.intent_canonicals import Intent
from app.services.rag_prompts import PROMPT_VERSION, build_system_prompt

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


# F81.d → F81.g — system prompt now lives in ``rag_prompts.py`` as a
# three-layer composition (identity + evidence rules + per-intent
# format rules + optional few-shot). See the module for the rationale
# behind each layer. This file just calls ``build_system_prompt(intent)``
# per request.

_CONTEXT_TEMPLATE = """\
--- Document: {filename} (chunk {chunk_index}){author_clause} ---
{text}
"""

# F104.a — candidate-summary block rendered before document chunks
# in the user prompt. Each hit corresponds to one candidate's
# recruiter-brief one-liner; the inline ``[filename]`` citation
# resolves the same way chunk citations do.
_CANDIDATE_TEMPLATE = """\
--- Candidate: {name} ---
{summary}{citation}
"""

_FALLBACK_NO_HITS = "Not in the provided documents."


@dataclass
class RagResult:
    answer: str
    citations: list[dict[str, Any]]
    model: str
    query_time_ms: int
    confidence: Confidence | None = None
    intent: Intent = "general"
    intent_confidence: float = 0.0


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
    intent: Intent
    intent_confidence: float


class RagService:
    def __init__(
        self,
        retriever: ChunkRetriever,
        llm: LlmProvider,
        classifier: IntentClassifier,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._classifier = classifier

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
            intent=ctx.intent,
            intent_confidence=ctx.intent_confidence,
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
                intent=ctx.intent,
                intent_confidence=ctx.intent_confidence,
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

        # F104.a — candidate-summary lane. Capped at
        # ``rag_max_candidate_hits`` so a flood of low-quality
        # matches doesn't crowd chunks out of the token budget.
        # Skipped when ``document_ids`` is set (caller pinned a
        # specific doc subset; candidate-level retrieval would
        # spuriously surface other candidates).
        candidates: list[Any] = []
        if document_ids is None:
            candidates = await self._retriever.retrieve_candidate_summaries(
                actor=actor,
                query=question,
                limit=settings.rag_max_candidate_hits,
            )

        if not chunks and not candidates:
            return None

        cutoff = settings.rag_context_max_distance
        budget = settings.rag_context_token_budget
        kept, tokens_used = self._apply_context_gate(chunks, cutoff, budget)
        if not kept and not candidates:
            logger.info(
                "rag context: 0/%d chunks kept (cutoff=%s, budget=%d)",
                len(chunks),
                "none" if cutoff is None else f"{cutoff:.2f}",
                budget,
            )
            return None

        # F81.g — classify intent, compose an intent-specific system
        # prompt. Classifier is CPU-bound and fast (single embed_query
        # call + cosine comparisons); no ``to_thread`` hop needed.
        intent_result = self._classifier.classify(question)
        system_prompt = build_system_prompt(intent_result.intent)

        context_parts: list[str] = []
        citations: list[dict[str, Any]] = []
        terms = extract_query_terms(question)

        # F104.a — candidate hits render *before* document chunks so
        # the LLM has the recruiter-shape anchor available before
        # detail-level chunks. Each hit produces one citation entry
        # with ``chunk_index = None`` — the FE renders these via the
        # same "filename + snippet" path as chunk citations.
        for cand in candidates:
            citation_marker = (
                f" [{cand.source_filename}]" if cand.source_filename else ""
            )
            context_parts.append(
                _CANDIDATE_TEMPLATE.format(
                    name=cand.name or "Unknown candidate",
                    summary=cand.summary,
                    citation=citation_marker,
                )
            )
            citations.append(
                {
                    "document_id": (
                        str(cand.source_document_id)
                        if cand.source_document_id is not None
                        else None
                    ),
                    "filename": cand.source_filename,
                    "chunk_index": None,
                    "text": cand.summary,
                    "match_spans": find_match_spans(cand.summary, terms),
                    "section_heading": None,
                    "page_number": None,
                }
            )

        for chunk in kept:
            # F103.c — surface the author when SearchService hydrated
            # one (either via Document.authored_by_id or the resume
            # self-link fallback). Empty string when unknown so the
            # header reads naturally for unattributed docs.
            author_clause = (
                f" — Authored by: {chunk.authored_by_name}"
                if chunk.authored_by_name
                else ""
            )
            context_parts.append(
                _CONTEXT_TEMPLATE.format(
                    filename=chunk.filename,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    author_clause=author_clause,
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

        # Single observability line per query — same grep-able format
        # across F81.b/c (chunks + tokens) and F81.g (intent + prompt
        # version). ``runner_up`` is how the operator diagnoses
        # near-tie classifications.
        logger.info(
            "rag context: %d/%d chunks kept, ~%d tokens "
            "(cutoff=%s, budget=%d) | intent=%s conf=%.2f runner=%s "
            "prompt=%s system_prompt_chars=%d",
            len(kept),
            len(chunks),
            tokens_used,
            "none" if cutoff is None else f"{cutoff:.2f}",
            budget,
            intent_result.intent,
            intent_result.confidence,
            intent_result.runner_up or "-",
            PROMPT_VERSION,
            len(system_prompt),
        )

        # F104.a — confidence is derived from the strongest signal
        # available. Chunks rank chunk-level retrieval quality;
        # candidate-summary hits carry distance from a different vector
        # space (one-line summary vs. context+chunk). When both are
        # present, prefer chunk distance for confidence (it's the
        # better-calibrated signal); when only candidates are present,
        # fall back to the top candidate's distance.
        if kept:
            confidence = _compute_confidence(kept)
        elif candidates:
            top_distance = candidates[0].distance
            if top_distance <= settings.rag_confidence_high_max_distance:
                confidence = "high"
            elif top_distance <= settings.rag_confidence_medium_max_distance:
                confidence = "medium"
            else:
                confidence = "low"
        else:
            # _build_context returned None earlier in this case; this
            # branch is unreachable but keeps the type checker happy.
            confidence = "low"

        return _RagContext(
            citations=citations,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            confidence=confidence,
            intent=intent_result.intent,
            intent_confidence=intent_result.confidence,
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
