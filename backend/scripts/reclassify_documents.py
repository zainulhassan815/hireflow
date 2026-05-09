"""F103.b — refresh ``metadata.skills`` on every READY document.

Re-runs the canonical skill matcher (`extract_skills`) against the
already-extracted text on every READY document, splices the result
into ``documents.metadata_['skills']``, and refreshes
``Candidate.skills`` for resumes via the existing
``SyncCandidateService`` hook.

Constraints (per F103.b plan, §"Backfill"):

- Never re-classifies ``document_type``. Calls ``extract_skills``
  directly — never invokes ``ExtractionService._classify`` — so a
  vocab change cannot silently re-route a doc into/out of the
  candidate pipeline.
- Skip-via-version-tag. Stamps
  ``metadata['skill_extraction_version'] = 'v1-narrative'``; subsequent
  runs skip docs already at that version. Crash-resumable.
- Snapshot before write. ``--apply`` requires ``--snapshot <path>``.
  Dumps the prior state per doc to JSONL — operator revert path.
- Batch commits per N=50 docs.
- ``--dry-run`` is the default; use ``--apply --snapshot snap.jsonl`` to
  write.

If a future ``PATCH /candidates/{id}`` exposes ``Candidate.skills`` to
HR users, the candidate-refresh step here would silently overwrite
their edits — revisit then.

Usage (from backend/):
    uv run python -m scripts.reclassify_documents
    uv run python -m scripts.reclassify_documents --apply --snapshot snap.jsonl
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

from app.core.db import SyncSessionLocal
from app.models import Candidate, Document, DocumentStatus, DocumentType
from app.services.skill_matcher import extract_skills
from app.services.sync_candidate_service import SyncCandidateService

logger = logging.getLogger(__name__)

SKILL_EXTRACTION_VERSION = "v1-narrative"
COMMIT_EVERY = 50


def _diff(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
    """Return ``(added, removed)`` between two skill lists."""
    bset, aset = set(before), set(after)
    return sorted(aset - bset), sorted(bset - aset)


def _snapshot_row(doc: Document, candidate: Candidate | None) -> dict:
    return {
        "document_id": str(doc.id),
        "candidate_id": str(candidate.id) if candidate else None,
        "document_skills_before": list((doc.metadata_ or {}).get("skills") or []),
        "candidate_skills_before": list(candidate.skills or []) if candidate else None,
    }


def _find_candidate(session: Session, doc: Document) -> Candidate | None:
    return session.execute(
        select(Candidate).where(Candidate.source_document_id == doc.id)
    ).scalar_one_or_none()


def _process_document(
    session: Session,
    doc: Document,
    *,
    apply: bool,
    snapshot: Iterable | None,
) -> tuple[bool, list[str], list[str]]:
    """Returns ``(changed, added, removed)``. When ``apply`` is False,
    no writes happen and ``snapshot`` is unused."""
    if not doc.extracted_text:
        return (False, [], [])

    before = list((doc.metadata_ or {}).get("skills") or [])
    after = extract_skills(doc.extracted_text)
    added, removed = _diff(before, after)
    changed = bool(added or removed)

    if not apply:
        return (changed, added, removed)

    candidate = (
        _find_candidate(session, doc)
        if doc.document_type == DocumentType.RESUME
        else None
    )

    if snapshot is not None:
        snapshot.write(json.dumps(_snapshot_row(doc, candidate)) + "\n")

    doc.metadata_ = {
        **(doc.metadata_ or {}),
        "skills": after,
        "skill_extraction_version": SKILL_EXTRACTION_VERSION,
    }

    if doc.document_type == DocumentType.RESUME:
        SyncCandidateService(session).handle_document_ready(doc)

    return (changed, added, removed)


def reclassify(*, apply: bool, snapshot_path: Path | None) -> None:
    if apply and snapshot_path is None:
        raise SystemExit("--apply requires --snapshot <path>")

    snapshot_cm = (
        snapshot_path.open("w", encoding="utf-8")
        if (apply and snapshot_path)
        else contextlib.nullcontext()
    )

    with snapshot_cm as snapshot_handle, SyncSessionLocal() as session:
        docs = list(
            session.execute(
                select(Document).where(Document.status == DocumentStatus.READY)
            ).scalars()
        )
        logger.info("found %d READY documents", len(docs))

        processed = changed_count = skipped = 0
        for i, doc in enumerate(docs, 1):
            version = (doc.metadata_ or {}).get("skill_extraction_version")
            if version == SKILL_EXTRACTION_VERSION:
                skipped += 1
                continue

            changed, added, removed = _process_document(
                session, doc, apply=apply, snapshot=snapshot_handle
            )
            processed += 1
            if changed:
                changed_count += 1
                logger.info(
                    "[%d/%d] %s: +%s -%s",
                    i,
                    len(docs),
                    doc.filename,
                    added or "[]",
                    removed or "[]",
                )

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
    reclassify(apply=args.apply, snapshot_path=args.snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
