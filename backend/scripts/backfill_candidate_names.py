"""F103.d — backfill ``Candidate.name`` (and ``metadata['name']``)
across the corpus by re-running the LLM classifier on existing resumes.

Why this exists: the rule-based classifier is high-confidence on
resume keywords and therefore short-circuits ``CompositeClassifier``
before the LLM ever runs — so resumes ingested via the rule-based
path never get ``metadata['name']`` populated, which means
``Candidate.name`` stays NULL, which means the F103.d entity-aware
contextualizer has no name to surface.

Strategy:

- Walk every READY resume.
- Run ``LlmClassifier.classify`` directly (skipping the composite
  threshold gate; we want the LLM signal regardless of rule-based
  confidence).
- Merge the LLM's metadata into ``Document.metadata_`` non-
  destructively (don't overwrite keys the LLM didn't return).
- Trigger ``SyncCandidateService.handle_document_ready`` so the new
  ``metadata['name']`` propagates to ``Candidate.name`` (and
  ``AuthorLinkageService.backfill_for_candidate`` runs per F103.c if
  the email also changed).
- Stamp ``metadata['name_backfill_version'] = 'v1-llm'``. Subsequent
  runs skip docs already stamped — single seam for resumability,
  matches F103.b/c precedent. Skip is by version tag *only*; whether
  the LLM extracted a name on the prior run is irrelevant.

Constraints baked in:

- Default ``--dry-run``. ``--apply`` requires ``--snapshot <path>``.
- Snapshot before write: per-doc
  ``{document_id, candidate_id, metadata_name_before,
  candidate_name_before}`` JSONL — operator revert path.
- Batch commits per N=50 docs.
- Real LLM calls cost money. ``--dry-run`` doesn't call the LLM at
  all so an operator can scope the work first.

Usage (from backend/):
    uv run python -m scripts.backfill_candidate_names
    uv run python -m scripts.backfill_candidate_names --apply --snapshot snap.jsonl
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

from app.adapters.classifiers.llm import LlmClassifier
from app.adapters.protocols import ClassificationResult
from app.core.config import settings
from app.core.db import SyncSessionLocal
from app.models import Candidate, Document, DocumentStatus, DocumentType
from app.services.sync_candidate_service import SyncCandidateService

logger = logging.getLogger(__name__)

NAME_BACKFILL_VERSION = "v1-llm"
COMMIT_EVERY = 50


def _build_classifier() -> LlmClassifier | None:
    """Construct an ``LlmClassifier`` straight from settings.

    The runtime classifier registry keys off ``vision_provider``
    (which bundles classification + OCR fallback into one switch).
    When that's set to ``tesseract`` (OCR-only), the runtime LLM
    classifier never fires — which is exactly the gap this backfill
    exists to close. So this script keys off ``llm_provider``
    directly: if a Claude or Ollama LLM is configured for *anything*,
    we use it for the name-extraction backfill regardless of the
    OCR/vision selector. Returns ``None`` if no LLM provider is
    configured.
    """
    from app.adapters.classifiers.llm import (
        create_claude_llm_call,
        create_ollama_llm_call,
    )

    provider = (settings.llm_provider or "").lower()
    if provider == "anthropic" and settings.anthropic_api_key:
        model = settings.llm_model or "claude-haiku-4-5-20251001"
        return LlmClassifier(
            create_claude_llm_call(settings.anthropic_api_key.get_secret_value(), model)
        )
    if provider == "ollama" and settings.ollama_base_url:
        model = settings.llm_model or "llava:13b"
        return LlmClassifier(create_ollama_llm_call(settings.ollama_base_url, model))
    return None


def _snapshot_row(doc: Document, candidate: Candidate | None) -> dict:
    metadata_name = (doc.metadata_ or {}).get("name")
    return {
        "document_id": str(doc.id),
        "candidate_id": str(candidate.id) if candidate else None,
        "metadata_name_before": metadata_name,
        "candidate_name_before": candidate.name if candidate else None,
    }


def _find_candidate(session: Session, doc: Document) -> Candidate | None:
    return session.execute(
        select(Candidate).where(Candidate.source_document_id == doc.id)
    ).scalar_one_or_none()


def _process_document(
    session: Session,
    doc: Document,
    classifier: LlmClassifier,
    *,
    apply: bool,
    snapshot: Iterable | None,
) -> tuple[bool, str]:
    """Returns ``(changed, status_label)``."""
    if not doc.extracted_text:
        return (False, "no-text")

    # LLM classifier call — synchronous, real network. Even on
    # ``--dry-run`` we want to scope the work, so we *do* call the
    # LLM in dry-run too. Operator gets honest cost visibility.
    try:
        result: ClassificationResult = classifier.classify(
            doc.extracted_text, doc.filename
        )
    except Exception:
        logger.exception("LLM classifier failed for %s", doc.filename)
        return (False, "classifier-error")

    new_name = (
        result.metadata.get("name") if isinstance(result.metadata, dict) else None
    )
    new_email = None
    new_skills = None
    if isinstance(result.metadata, dict):
        emails = result.metadata.get("emails") or []
        if isinstance(emails, list) and emails:
            new_email = emails[0]
        skills = result.metadata.get("skills") or []
        if isinstance(skills, list) and skills:
            new_skills = sorted({s for s in skills if isinstance(s, str) and s})

    candidate = _find_candidate(session, doc)
    metadata_name_before = (doc.metadata_ or {}).get("name")
    candidate_name_before = candidate.name if candidate else None

    summary = f"name='{new_name}' email='{new_email}' skills={len(new_skills or [])}"

    if not apply:
        return (
            bool(new_name) and new_name != metadata_name_before,
            f"would-update {summary}",
        )

    if snapshot is not None:
        snapshot.write(json.dumps(_snapshot_row(doc, candidate)) + "\n")

    # Non-destructive merge: only overwrite when the LLM produced a
    # value. ``skill_extraction_version`` and other prior version
    # stamps stay intact.
    merged: dict = dict(doc.metadata_ or {})
    if new_name:
        merged["name"] = new_name
    if new_email:
        merged.setdefault("emails", [])
        if new_email.lower() not in {
            e.lower() for e in merged["emails"] if isinstance(e, str)
        }:
            merged["emails"] = sorted({*merged["emails"], new_email.lower()})
    if new_skills is not None:
        # Union with any pre-existing skills list — non-destructive.
        existing = (
            merged.get("skills") or [] if isinstance(merged.get("skills"), list) else []
        )
        merged["skills"] = sorted({*existing, *new_skills})
    merged["name_backfill_version"] = NAME_BACKFILL_VERSION
    doc.metadata_ = merged

    # Propagate to ``Candidate.name`` via the existing sync hook,
    # which also kicks the F103.c author-linkage backfill if the
    # candidate's email changed.
    SyncCandidateService(session).handle_document_ready(doc)

    return (
        bool(new_name) and new_name != candidate_name_before,
        f"updated {summary}",
    )


def backfill(*, apply: bool, snapshot_path: Path | None) -> None:
    if apply and snapshot_path is None:
        raise SystemExit("--apply requires --snapshot <path>")

    classifier = _build_classifier()
    if classifier is None:
        raise SystemExit(
            "No LLM provider configured. Set LLM_PROVIDER + the matching "
            "API_KEY / BASE_URL env vars and retry."
        )

    snapshot_cm = (
        snapshot_path.open("w", encoding="utf-8")
        if (apply and snapshot_path)
        else contextlib.nullcontext()
    )

    with snapshot_cm as snapshot_handle, SyncSessionLocal() as session:
        docs = list(
            session.execute(
                select(Document).where(
                    Document.status == DocumentStatus.READY,
                    Document.document_type == DocumentType.RESUME,
                )
            ).scalars()
        )
        logger.info("found %d READY resumes", len(docs))

        processed = changed_count = skipped = 0
        for i, doc in enumerate(docs, 1):
            version = (doc.metadata_ or {}).get("name_backfill_version")
            if version == NAME_BACKFILL_VERSION:
                skipped += 1
                continue

            changed, status = _process_document(
                session, doc, classifier, apply=apply, snapshot=snapshot_handle
            )
            processed += 1
            if changed:
                changed_count += 1
            logger.info("[%d/%d] %s: %s", i, len(docs), doc.filename, status)

            if apply and processed % COMMIT_EVERY == 0:
                session.commit()
                if snapshot_handle is not None:
                    snapshot_handle.flush()
                logger.info("committed batch (%d processed)", processed)

        if apply:
            session.commit()

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
