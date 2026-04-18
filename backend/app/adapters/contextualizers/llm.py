"""LLM-backed chunk contextualizer (F82.c).

Takes any ``LlmProvider`` — Claude, Ollama, future adapters — and uses
it to generate a short context for each chunk. The context is prepended
to the chunk's text at embed time (not display time), raising retrieval
accuracy without changing what the user sees in snippets.

Three modes:

- ``summary`` (universal, cheap): 1 LLM call to summarize the whole
  document, N per-chunk calls with summary + chunk.
- ``full_doc`` (small docs, prompt-caching backends): N calls each
  including the entire document body. Best quality but scales with
  document size — expensive on local models without caching.
- ``auto`` (default): pick per-doc based on extracted-text length.
  Small docs → ``full_doc``; large docs → ``summary``.

Design:

- Works with any ``LlmProvider``; no vendor lock.
- Per-chunk failures are non-fatal — chunks that can't be
  contextualized keep ``context=None`` and get embedded as plain text.
- Summary failure falls back to ``"Document: {filename}"``.
- Serial per-chunk calls today. Parallel is a follow-up if latency
  becomes a bottleneck.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.adapters.protocols import LlmProvider
    from app.models import Document
    from app.services.chunking import Chunk

logger = logging.getLogger(__name__)


# Bumped when the prompts or modes change in a way that invalidates
# previously-stored contexts. Stamped on each doc as
# ``contextualization_version``.
CONTEXTUALIZATION_VERSION = "v1-haiku-summary-or-fulldoc"

_MODES = frozenset({"summary", "full_doc", "auto"})

# Cap on the summary-prompt body to keep token count bounded for very
# large docs. 30K chars ≈ 7.5K tokens — fine for Haiku, fits local too.
_SUMMARIZE_MAX_CHARS = 30_000

_SUMMARIZER_SYSTEM_PROMPT = (
    "You write compact document summaries for search indexing. "
    "Include the document's topic, purpose, and main sections. "
    "Every sentence should carry retrieval signal. "
    "Answer ONLY with the summary text — no preamble, no formatting, "
    "no markdown."
)

_SUMMARIZER_USER_TEMPLATE = """Summarize this document in 100-200 words for search indexing.

Filename: {filename}

<document>
{body}
</document>"""


_SITUATE_SYSTEM_PROMPT = (
    "You situate text chunks within their source document for search "
    "indexing. Produce a short context (50-100 words) describing: the "
    "document's topic, the section this chunk belongs to, and what "
    "the chunk specifically covers. "
    "Answer ONLY with the context text — no preamble, no formatting, "
    "no markdown, no bullet points."
)

_SITUATE_USER_TEMPLATE = """Document filename: {filename}

<document_context>
{doc_context}
</document_context>

<chunk>
{chunk_text}
</chunk>

Write 50-100 words situating this chunk within the document for search retrieval."""


class LlmChunkContextualizer:
    """``ChunkContextualizer`` implementation backed by any ``LlmProvider``."""

    def __init__(
        self,
        llm: LlmProvider,
        *,
        mode: str = "auto",
        full_doc_max_chars: int = 8000,
    ) -> None:
        if mode not in _MODES:
            raise ValueError(
                f"Unknown contextualizer mode {mode!r}. "
                f"Expected one of: {sorted(_MODES)}."
            )
        self._llm = llm
        self._mode = mode
        self._full_doc_max_chars = full_doc_max_chars

    @property
    def model_name(self) -> str:
        return self._llm.model_name

    def contextualize(self, document: Document, chunks: list[Chunk]) -> list[Chunk]:
        if not chunks:
            return chunks

        mode = self._resolve_mode(document)
        doc_context = self._build_doc_context(document, mode)

        out: list[Chunk] = []
        for chunk in chunks:
            context = self._situate(document, chunk, doc_context)
            out.append(replace(chunk, context=context))
        return out

    # ---- internal ----

    def _resolve_mode(self, document: Document) -> str:
        """Translate ``auto`` into a concrete mode given the doc size."""
        if self._mode != "auto":
            return self._mode
        size = len(document.extracted_text or "")
        return "full_doc" if size <= self._full_doc_max_chars else "summary"

    def _build_doc_context(self, document: Document, mode: str) -> str:
        """Return the document-level context prefix used for each chunk call.

        - ``full_doc`` mode: the extracted text itself (truncated to a
          cap so a pathologically huge doc doesn't blow tokens).
        - ``summary`` mode: a single LLM call to summarize the doc.
        """
        body = (document.extracted_text or "").strip()
        if not body:
            return f"Document: {document.filename}"

        if mode == "full_doc":
            # Hard cap so an outlier doc can't spike token cost per chunk.
            return body[:_SUMMARIZE_MAX_CHARS]

        # summary mode
        try:
            summary = self._llm.complete(
                system=_SUMMARIZER_SYSTEM_PROMPT,
                user=_SUMMARIZER_USER_TEMPLATE.format(
                    filename=document.filename,
                    body=body[:_SUMMARIZE_MAX_CHARS],
                ),
            ).strip()
            if not summary:
                raise RuntimeError("empty summary from LLM")
            return summary
        except Exception:
            logger.exception(
                "summarization failed for %s; falling back to filename prefix",
                document.id,
            )
            return f"Document: {document.filename}"

    def _situate(
        self, document: Document, chunk: Chunk, doc_context: str
    ) -> str | None:
        """One LLM call: situate a single chunk.

        Returns the context text on success, ``None`` on failure.
        Caller prepends context to chunk.text at embed time.
        """
        try:
            context = self._llm.complete(
                system=_SITUATE_SYSTEM_PROMPT,
                user=_SITUATE_USER_TEMPLATE.format(
                    filename=document.filename,
                    doc_context=doc_context,
                    chunk_text=chunk.text,
                ),
            ).strip()
            return context or None
        except Exception:
            logger.warning(
                "per-chunk contextualization failed for doc %s chunk_index=%s",
                document.id,
                chunk.metadata.get("chunk_index"),
                exc_info=True,
            )
            return None
