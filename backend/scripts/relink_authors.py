"""F103.c — backfill ``Document.authored_by_id`` across the corpus.

For every READY document, ensure ``metadata.emails`` is populated
(running the same regex the classifier uses if needed), then look up
a matching candidate by email and set the FK. Mirrors the F103.b
``reclassify_documents`` shape: idempotent, dry-run by default,
snapshot-required on apply, version-tag-skip for resumability.

Constraints:

- Default ``--dry-run``. ``--apply`` requires ``--snapshot <path>``.
- **Never overwrites an existing ``authored_by_id``.** If the auto-
  inference picked the wrong candidate (rare, but possible — old
  email lingering in a footer), the operator's escape hatch is
  direct SQL: ``UPDATE documents SET authored_by_id = NULL WHERE
  id = ?``. A ``--force`` flag is intentionally not added — premature
  until false-positives are observed at scale.
- Skip-via-version-tag. Stamps
  ``metadata['author_linkage_version'] = 'v1-email'``; subsequent
  runs skip docs already at that version. Crash-resumable.
- Snapshot before write: ``{document_id, authored_by_before,
  emails_used}`` per processed doc.
- Batch commits per N=50 docs. (Pattern-matched from F103.b for
  consistency; current corpus is tiny — this is for future-proofing,
  not a real constraint at today's scale.)

Usage (from backend/):
    uv run python -m scripts.relink_authors
    uv run python -m scripts.relink_authors --apply --snapshot snap.jsonl
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SyncSessionLocal
from app.models import Candidate, Document, DocumentStatus

logger = logging.getLogger(__name__)

AUTHOR_LINKAGE_VERSION = "v1-email"
COMMIT_EVERY = 50

# Same regex ``RuleBasedClassifier`` uses, copied here so the script
# can repair docs whose ``metadata.emails`` was never written (legacy
# rows ingested before F103.c lifted the resume gate).
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _ensure_emails_metadata(doc: Document) -> list[str]:
    """Return the lowercased emails for this doc, repairing
    ``metadata.emails`` in place if absent."""
    existing = (doc.metadata_ or {}).get("emails") or []
    normalised = sorted({e.strip().lower() for e in existing if isinstance(e, str)})
    if normalised:
        return normalised
    if not doc.extracted_text:
        return []
    found = sorted(
        {m.group(0).lower() for m in _EMAIL_PATTERN.finditer(doc.extracted_text)}
    )
    if found:
        doc.metadata_ = {**(doc.metadata_ or {}), "emails": found}
    return found


def _find_candidate_by_email(
    session: Session, owner_id, emails: list[str]
) -> Candidate | None:
    if not emails:
        return None
    candidates = list(
        session.execute(
            select(Candidate).where(
                Candidate.owner_id == owner_id,
                Candidate.email.in_(emails),
            )
        ).scalars()
    )
    if not candidates:
        # Try a case-insensitive comparison in Python — handles candidate
        # rows that were written before F103.c lowercased everything.
        lower_emails = {e.lower() for e in emails}
        all_candidates = list(
            session.execute(
                select(Candidate).where(
                    Candidate.owner_id == owner_id,
                    Candidate.email.is_not(None),
                )
            ).scalars()
        )
        candidates = [c for c in all_candidates if c.email.lower() in lower_emails]
    if not candidates:
        return None
    if len(candidates) > 1:
        logger.warning(
            "doc owner %s: %d candidates matched emails=%s; picking %s",
            owner_id,
            len(candidates),
            emails,
            candidates[0].id,
        )
    return candidates[0]


def _snapshot_row(doc: Document, emails: list[str]) -> dict:
    return {
        "document_id": str(doc.id),
        "authored_by_before": str(doc.authored_by_id) if doc.authored_by_id else None,
        "emails_used": emails,
    }


def _process_document(
    session: Session,
    doc: Document,
    *,
    apply: bool,
    snapshot: Iterable | None,
) -> tuple[bool, str | None]:
    """Returns ``(changed, status)``. ``status`` is a short string
    summarising the outcome for the per-doc log line."""
    from app.models import AuthorSource

    if doc.authored_by_id is not None:
        return (False, "already-linked")
    # F103.c.2 — also skip docs whose author was once set manually
    # but whose candidate has since been deleted (FK now NULL,
    # source still 'manual' due to ON DELETE SET NULL leaving the
    # source dangling). The operator explicitly chose this doc's
    # author once; auto-relinking to a different candidate would
    # silently undo that choice.
    if doc.authored_by_source == AuthorSource.MANUAL:
        return (False, "manual-source-skipped")

    emails = _ensure_emails_metadata(doc)
    if not emails:
        return (False, "no-emails")

    candidate = _find_candidate_by_email(session, doc.owner_id, emails)
    if candidate is None:
        return (False, "no-candidate-match")

    if not apply:
        return (True, f"would-link → {candidate.id}")

    if snapshot is not None:
        snapshot.write(json.dumps(_snapshot_row(doc, emails)) + "\n")

    doc.authored_by_id = candidate.id
    doc.authored_by_source = AuthorSource.EMAIL_MATCH
    doc.metadata_ = {
        **(doc.metadata_ or {}),
        "author_linkage_version": AUTHOR_LINKAGE_VERSION,
    }
    return (True, f"linked → {candidate.id}")


def relink(*, apply: bool, snapshot_path: Path | None) -> None:
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
            version = (doc.metadata_ or {}).get("author_linkage_version")
            if version == AUTHOR_LINKAGE_VERSION:
                skipped += 1
                continue

            changed, status = _process_document(
                session, doc, apply=apply, snapshot=snapshot_handle
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
            "done. processed=%d linked=%d skipped(version)=%d %s",
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

    relink(apply=args.apply, snapshot_path=args.snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
