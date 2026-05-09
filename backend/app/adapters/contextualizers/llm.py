"""LLM-backed chunk contextualizer (F82.c, F103.d).

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

F103.d entity-aware prompts:

- Both prompts now know the document's author (from
  ``Document.authored_by`` per F103.c, falling back to
  ``metadata['name']``) and the classifier's extracted technology
  list (from F103.b's ``metadata['skills']``).
- The summary and per-chunk prompts both instruct the LLM to
  preserve agency — when the chunk describes work the named author
  did, attribute by name rather than stripping to passive voice.
- ``contextualize()`` stamps
  ``metadata['contextualization_version']`` at the end of a
  successful pass so a future targeted re-embed can identify
  stale-prompt docs without a schema change.

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
# ``metadata['contextualization_version']`` after a successful
# ``contextualize()`` pass.
CONTEXTUALIZATION_VERSION = "v2-haiku-entity-aware"

_MODES = frozenset({"summary", "full_doc", "auto"})

# Cap on the summary-prompt body to keep token count bounded for very
# large docs. 30K chars ≈ 7.5K tokens — fine for Haiku, fits local too.
_SUMMARIZE_MAX_CHARS = 30_000

# Skills list is ``KNOWN_SKILLS``-bounded today (~80 entries max in the
# vocab); 50 is well above the practical hits-per-doc max while keeping
# the prompt token bill bounded if the cap ever fires.
_MAX_SKILLS_IN_PROMPT = 50

_SUMMARIZER_SYSTEM_PROMPT = (
    "You write compact document summaries for search indexing. The "
    "reader is a search system, not a human; every sentence should "
    "carry retrieval signal. When the document's author is known, "
    "name them by name when describing what the document covers. "
    "Reference specific technologies, organizations, products, and "
    "metrics rather than generic terms. Preserve agency: when the "
    "document describes work the named author did, attribute it to "
    "them by name (do not strip to passive voice). Answer ONLY with "
    "the summary text — no preamble, no formatting, no markdown."
)

_SUMMARIZER_USER_TEMPLATE = """Filename: {filename}
Author: {author_clause}
Technologies mentioned in this document: {tech_clause}

<document>
{body}
</document>

Summarize this document in 100-200 words for search indexing."""


_SITUATE_SYSTEM_PROMPT = (
    "You situate text chunks within their source document for search "
    "indexing. Produce a short context (50-100 words) covering: who "
    "authored this document (name them when known), what the chunk "
    "specifically covers, the specific technologies / products / "
    "companies named in the chunk, and how the chunk relates to the "
    "broader document. Preserve agency: when the chunk describes "
    "work the document's author did, attribute it to them by name. "
    "Use the provided technology list rather than generic terms when "
    "the chunk references those technologies. Answer ONLY with the "
    "context text — no preamble, no formatting, no markdown, no "
    "bullet points."
)

_SITUATE_USER_TEMPLATE = """Document filename: {filename}
Author: {author_clause}
Technologies mentioned in this document: {tech_clause}

<document_context>
{doc_context}
</document_context>

<chunk>
{chunk_text}
</chunk>

Write 50-100 words situating this chunk within the document for search retrieval."""


def _resolve_author(document: Document) -> str:
    """Return the author label for prompt rendering.

    Resolution order — preferred:
      1. ``Document.authored_by.name`` (F103.c link).
      2. ``metadata['name']`` (LLM classifier slot, may be stale if a
         candidate was edited after ingest).
      3. ``"unknown"`` sentinel.
    Logs an INFO line when the metadata fallback fires so an
    operator can audit stale-name cases without scraping prompts.
    """
    linked = getattr(document, "authored_by", None)
    if linked is not None and linked.name:
        return linked.name
    metadata_name = (document.metadata_ or {}).get("name")
    if isinstance(metadata_name, str) and metadata_name.strip():
        logger.info(
            "contextualizer: using metadata.name fallback for doc %s",
            document.id,
        )
        return metadata_name.strip()
    return "unknown"


def _resolve_tech_clause(document: Document) -> str:
    """Render ``metadata['skills']`` as a comma-joined clause for the
    prompt. Capped at ``_MAX_SKILLS_IN_PROMPT`` with an explicit
    truncation hint so the LLM doesn't treat the visible set as
    exhaustive."""
    raw = (document.metadata_ or {}).get("skills") or []
    skills = sorted({s for s in raw if isinstance(s, str) and s})
    if not skills:
        return "(none extracted)"
    if len(skills) <= _MAX_SKILLS_IN_PROMPT:
        return ", ".join(skills)
    head = ", ".join(skills[:_MAX_SKILLS_IN_PROMPT])
    return f"{head}, …and {len(skills) - _MAX_SKILLS_IN_PROMPT} more"


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
        author_clause = _resolve_author(document)
        tech_clause = _resolve_tech_clause(document)
        doc_context = self._build_doc_context(
            document, mode, author_clause, tech_clause
        )

        out: list[Chunk] = []
        for chunk in chunks:
            context = self._situate(
                document, chunk, doc_context, author_clause, tech_clause
            )
            out.append(replace(chunk, context=context))

        # Stamp version on the document so a future targeted re-embed
        # can find docs with stale-prompt context. Owned here (the only
        # seam that runs the prompt) rather than in the embedding
        # service which has no honest way to know which version
        # produced the chunks it consumes.
        document.metadata_ = {
            **(document.metadata_ or {}),
            "contextualization_version": CONTEXTUALIZATION_VERSION,
        }
        return out

    # ---- internal ----

    def _resolve_mode(self, document: Document) -> str:
        """Translate ``auto`` into a concrete mode given the doc size."""
        if self._mode != "auto":
            return self._mode
        size = len(document.extracted_text or "")
        return "full_doc" if size <= self._full_doc_max_chars else "summary"

    def _build_doc_context(
        self,
        document: Document,
        mode: str,
        author_clause: str,
        tech_clause: str,
    ) -> str:
        """Return the document-level context prefix used for each chunk call.

        - ``full_doc`` mode: the extracted text itself (truncated to a
          cap so a pathologically huge doc doesn't blow tokens).
        - ``summary`` mode: a single LLM call to summarize the doc.
        """
        body = (document.extracted_text or "").strip()
        if not body:
            return f"Document: {document.filename} (Author: {author_clause})"

        if mode == "full_doc":
            # Hard cap so an outlier doc can't spike token cost per chunk.
            return body[:_SUMMARIZE_MAX_CHARS]

        # summary mode
        try:
            summary = self._llm.complete(
                system=_SUMMARIZER_SYSTEM_PROMPT,
                user=_SUMMARIZER_USER_TEMPLATE.format(
                    filename=document.filename,
                    author_clause=author_clause,
                    tech_clause=tech_clause,
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
            return f"Document: {document.filename} (Author: {author_clause})"

    def _situate(
        self,
        document: Document,
        chunk: Chunk,
        doc_context: str,
        author_clause: str,
        tech_clause: str,
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
                    author_clause=author_clause,
                    tech_clause=tech_clause,
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
