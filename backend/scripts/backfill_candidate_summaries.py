"""F104.a — generate per-candidate recruiter brief + index it.

Walks every candidate (or a filtered subset) and:

1. Loads the source resume's extracted text (when
   ``candidate.source_document_id`` is set).
2. Calls ``CandidateSummaryService.generate_for(...)`` which writes
   the summary text + ``summary_version`` to the candidate row.
3. The service also embeds the summary and upserts into the
   candidate-similarity Chroma collection so the F104.a retrieval
   lane can find it.

Constraints (mirrors F103.b/c/d backfills):

- Default ``--dry-run``. ``--apply`` requires ``--snapshot <path>``.
- Skip-via-version-tag: process iff
  ``candidate.summary_version != SUMMARY_VERSION``. Bumping the
  ``SUMMARY_VERSION`` constant in ``CandidateSummaryService`` is
  the rerun signal — every candidate flips to the new version on
  the next run.
- Snapshot before write: per-candidate JSONL row with prior
  state for operator revert.
- Real LLM + real Chroma calls (not stubbed). ``--dry-run`` does
  no network calls so an operator can scope cost first.

Usage (from backend/):
    uv run python -m scripts.backfill_candidate_summaries
    uv run python -m scripts.backfill_candidate_summaries --apply --snapshot snap.jsonl
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import sys
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SyncSessionLocal
from app.models import Candidate, Document
from app.services.candidate_summary_service import (
    SUMMARY_VERSION,
    CandidateSummaryService,
)

logger = logging.getLogger(__name__)


def _build_llm_call() -> object | None:
    """Mirror the runtime selection (F103.d's name-backfill pattern)."""
    provider = (settings.llm_provider or "").lower()
    if provider == "anthropic" and settings.anthropic_api_key:
        from app.adapters.classifiers.llm import create_claude_llm_call

        return create_claude_llm_call(
            settings.anthropic_api_key.get_secret_value(),
            settings.llm_model,
        )
    if provider == "ollama" and settings.ollama_base_url:
        from app.adapters.classifiers.llm import create_ollama_llm_call

        return create_ollama_llm_call(settings.ollama_base_url, settings.llm_model)
    return None


def _build_chroma() -> tuple[object | None, object | None]:
    """Returns ``(embedder, store)``; both ``None`` when Chroma is
    unavailable. The script still writes the summary text in that
    case — the retrieval lane just stays empty until the next run."""
    try:
        from app.adapters.chroma_store import ChromaVectorStore
        from app.adapters.embeddings.registry import get_embedding_provider

        embedder = get_embedding_provider(settings)
        store = ChromaVectorStore(
            host=settings.chroma_host,
            port=settings.chroma_port,
            embedder=embedder,
        )
        return embedder, store
    except Exception:
        logger.warning("ChromaDB unavailable; will write summaries without indexing")
        return None, None


def _snapshot_row(candidate: Candidate) -> dict:
    return {
        "candidate_id": str(candidate.id),
        "summary_before": candidate.summary,
        "summary_version_before": candidate.summary_version,
    }


def _resume_text(session: Session, candidate: Candidate) -> str | None:
    if candidate.source_document_id is None:
        return None
    doc = session.get(Document, candidate.source_document_id)
    return doc.extracted_text if doc else None


def _process_candidate(
    session: Session,
    candidate: Candidate,
    *,
    apply: bool,
    snapshot: Iterable | None,
    service: CandidateSummaryService | None,
) -> tuple[bool, str]:
    """Returns ``(changed, status_label)``."""
    if candidate.summary_version == SUMMARY_VERSION:
        return (False, f"already-v={SUMMARY_VERSION}")

    resume_text = _resume_text(session, candidate)

    if not apply:
        # Dry-run: no LLM call, no DB write, no Chroma upsert.
        # Operator gets a count + per-candidate plan without cost.
        return (
            True,
            f"would-summarise (resume_text={'yes' if resume_text else 'no'})",
        )

    if service is None:
        return (False, "no-llm-provider")

    if snapshot is not None:
        snapshot.write(json.dumps(_snapshot_row(candidate)) + "\n")

    summary = service.generate_for(candidate, resume_text=resume_text)
    if summary is None:
        return (False, "llm-failed")
    return (True, f"summarised ({len(summary)} chars)")


def backfill(*, apply: bool, snapshot_path: Path | None) -> None:
    if apply and snapshot_path is None:
        raise SystemExit("--apply requires --snapshot <path>")

    llm_call = _build_llm_call()
    embedder, store = _build_chroma()

    if apply and llm_call is None:
        raise SystemExit(
            "No LLM provider configured. Set LLM_PROVIDER + the "
            "matching API_KEY / BASE_URL env vars and retry."
        )

    snapshot_cm = (
        snapshot_path.open("w", encoding="utf-8")
        if (apply and snapshot_path)
        else contextlib.nullcontext()
    )

    with snapshot_cm as snapshot_handle, SyncSessionLocal() as session:
        candidates = list(
            session.execute(select(Candidate).order_by(Candidate.created_at)).scalars()
        )
        logger.info("found %d candidates", len(candidates))

        service: CandidateSummaryService | None = None
        if apply and llm_call is not None:
            service = CandidateSummaryService(
                session,
                llm_call,  # type: ignore[arg-type]
                embedder=embedder,  # type: ignore[arg-type]
                store=store,  # type: ignore[arg-type]
            )

        processed = changed_count = skipped = 0
        for i, candidate in enumerate(candidates, 1):
            label = candidate.name or candidate.email or str(candidate.id)
            if candidate.summary_version == SUMMARY_VERSION:
                skipped += 1
                logger.info(
                    "[%d/%d] %s: skip (version=%s)",
                    i,
                    len(candidates),
                    label,
                    SUMMARY_VERSION,
                )
                continue

            changed, status = _process_candidate(
                session,
                candidate,
                apply=apply,
                snapshot=snapshot_handle,
                service=service,
            )
            processed += 1
            if changed:
                changed_count += 1
            logger.info("[%d/%d] %s: %s", i, len(candidates), label, status)

        logger.info(
            "done. processed=%d changed=%d skipped(version)=%d %s",
            processed,
            changed_count,
            skipped,
            "(dry-run)" if not apply else "",
        )


def main() -> int:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes. Default is dry-run.",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="Required with --apply. JSONL file capturing pre-write state.",
    )
    args = parser.parse_args()

    backfill(apply=args.apply, snapshot_path=args.snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
