"""F104.a — generate per-candidate recruiter brief at ingestion.

One-sentence summary in a fixed shape:

  ``{Name} — {role/seniority}, {experience}, {primary tech list}.``

Worker-side service (sync session, never raises into the caller's
transaction) symmetric with ``SyncCandidateService`` and
``AuthorLinkageService``. Called from the
``SyncCandidateService._create_or_update`` tail after the
candidate row has committed; takes the candidate's structured
fields plus the resume's extracted text (when available) and asks
the LLM for a recruiter-brief in one sentence.

The summary is retrievable as a separate vector in Chroma (see
F104.a §5 + the new ``CandidateSimilarityStore`` protocol). The
LLM call here only writes the *text*; embedding + Chroma upsert
happen separately so ingest doesn't depend on Chroma being up.

Version-stamped via ``summary_version`` so a future prompt
rewrite can be detected by the backfill script: bump
``SUMMARY_VERSION`` here, the backfill skip predicate fires.
Mirrors F103.b/c/d's version-tag pattern.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.adapters.classifiers.llm import LlmCallable
    from app.adapters.protocols import (
        CandidateSimilarityStore,
        EmbeddingProvider,
    )
    from app.models import Candidate

logger = logging.getLogger(__name__)


# Bumped when the system prompt or the input shape changes in a way
# that invalidates previously-stored summaries. Stamped on each
# candidate as ``summary_version``.
SUMMARY_VERSION = "v1-haiku-recruiter-brief"

# Cap on resume body included in the user message so the prompt
# stays bounded on Haiku.
_RESUME_MAX_CHARS = 5_000

_SYSTEM_PROMPT = (
    "You write one-sentence candidate summaries for an HR search "
    "system.\n\n"
    "Format:\n"
    "  {Name} — {role/seniority}, {experience}, {primary tech list}.\n\n"
    "Rules:\n"
    "- Use the structured fields verbatim when they exist (don't "
    "paraphrase a name or change a skill spelling).\n"
    "- Pick 3–5 most prominent technologies; prefer specific names "
    '("Stripe", "FastAPI") over categories ("payments", "backend").\n'
    '- If experience_years is set, use "{n}+ yrs" or "{n} yrs"; '
    "never invent a number.\n"
    "- If the role isn't obvious from the data, omit the "
    "role/seniority segment.\n"
    "- One sentence. No preamble. No markdown."
)


def _build_user_message(candidate: Candidate, resume_text: str | None) -> str:
    """Compose the user message with structured fields + resume body."""
    structured: list[str] = []
    if candidate.name:
        structured.append(f"Name: {candidate.name}")
    if candidate.email:
        structured.append(f"Email: {candidate.email}")
    if candidate.experience_years is not None:
        structured.append(f"Experience years: {candidate.experience_years}")
    if candidate.skills:
        structured.append(f"Skills: {', '.join(candidate.skills)}")
    if candidate.education:
        structured.append(f"Education: {', '.join(candidate.education)}")

    parts = ["Candidate fields:", *structured]
    if resume_text:
        body = resume_text.strip()
        if len(body) > _RESUME_MAX_CHARS:
            body = body[:_RESUME_MAX_CHARS]
        parts.append("")
        parts.append("Resume body:")
        parts.append(body)
    parts.append("")
    parts.append("Write the one-sentence summary now.")
    return "\n".join(parts)


class CandidateSummaryService:
    """Worker-side. Never raises into the caller's transaction.

    Two responsibilities:

    1. Generate the summary text via the LLM and write it to
       ``candidate.summary`` + ``candidate.summary_version``.
    2. Embed the summary and upsert into the candidate-similarity
       store so the F104.a retrieval lane can find it.

    Either step can fail independently. The text-write happens
    first; if the embed/upsert fails, the candidate row keeps the
    summary (the retrieval lane just won't surface it until the
    backfill script re-runs and tries again).
    """

    def __init__(
        self,
        session: Session,
        llm_call: LlmCallable,
        *,
        embedder: EmbeddingProvider | None = None,
        store: CandidateSimilarityStore | None = None,
    ) -> None:
        self._session = session
        self._llm_call = llm_call
        # Optional — when None, the service generates the text but
        # doesn't index it in Chroma (e.g., test paths or environments
        # where Chroma isn't configured).
        self._embedder = embedder
        self._store = store

    def generate_for(
        self,
        candidate: Candidate,
        *,
        resume_text: str | None = None,
    ) -> str | None:
        """Synthesise the summary, write to the candidate row, and
        upsert the embedding into the candidate-similarity store.

        Returns the summary text on success, ``None`` on LLM
        failure. Never raises; logs at WARNING. Caller commits the
        session.
        """
        try:
            user = _build_user_message(candidate, resume_text)
            summary = self._llm_call(_SYSTEM_PROMPT, user).strip()
        except Exception:
            logger.exception("candidate summary generation failed for %s", candidate.id)
            return None

        if not summary:
            logger.warning("candidate summary empty for %s; leaving NULL", candidate.id)
            return None

        # Hard-cap to the column length so a chatty LLM doesn't
        # blow the schema. 1024 chars is plenty for one substantial
        # sentence; truncation is the safe fail-mode.
        if len(summary) > 1024:
            summary = summary[:1024]

        candidate.summary = summary
        candidate.summary_version = SUMMARY_VERSION
        self._session.commit()

        logger.info(
            "candidate summary written for %s (%d chars, version=%s)",
            candidate.id,
            len(summary),
            SUMMARY_VERSION,
        )

        # Index the summary in the candidate-similarity store. Failure
        # here doesn't roll back the text write — the row keeps the
        # summary; the retrieval lane just won't surface it until
        # the backfill script re-runs.
        self._index_summary(candidate, summary)

        return summary

    def _index_summary(self, candidate: Candidate, summary: str) -> None:
        if self._embedder is None or self._store is None:
            return
        try:
            embedding = self._embedder.embed_documents([summary])[0]
            metadata: dict[str, object] = {
                "owner_id": str(candidate.owner_id),
                "candidate_id": str(candidate.id),
                "summary_version": SUMMARY_VERSION,
            }
            if candidate.source_document_id is not None:
                metadata["source_document_id"] = str(candidate.source_document_id)
            self._store.upsert_candidate_summary(
                str(candidate.id),
                summary=summary,
                embedding=embedding,
                metadata=metadata,
            )
        except Exception:
            logger.warning(
                "candidate summary indexing failed for %s (text saved)",
                candidate.id,
                exc_info=True,
            )


__all__ = ["CandidateSummaryService", "SUMMARY_VERSION"]
