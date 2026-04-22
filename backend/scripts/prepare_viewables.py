"""Backfill viewable assets for already-processed documents (F105.b).

F105.b's ingest pipeline prepares the viewable asset (converts docx /
pptx / etc to PDF and stores it under ``viewable/<doc_id>.pdf``) as a
post-extraction step. Documents uploaded before F105.b landed have
``viewable_kind`` / ``viewable_key`` NULL and render as
``kind="unsupported"`` with ``meta.reason="conversion_pending"`` until
this script runs.

Unlike ``reextract_all.py``, this script does **not** re-run extraction
— it calls ``ViewerPreparationService.prepare`` directly, which is
~60× cheaper because it skips Unstructured / embeddings / the
contextualizer.

Behavior:
- Default: process every READY document with NULL viewable columns.
- ``--force``: re-process every READY document regardless (useful after
  bumping the conversion strategy or swapping providers). Safe
  because prep is idempotent — same doc id → same viewable key.
- ``--dry-run``: print what would run, touch nothing.
- ``--limit N``: cap the number of docs processed per run, useful for
  smoke-testing on a subset.

Graceful degradation: if LibreOffice isn't installed,
``ViewerPreparationService`` logs a warning per doc and moves on.
Office docs stay ``conversion_pending`` until the binary is available.
PDFs and images have their passthrough ``prepare`` — those always
succeed and are cheap.

Usage (from backend/):
    uv run python -m scripts.prepare_viewables
    uv run python -m scripts.prepare_viewables --dry-run
    uv run python -m scripts.prepare_viewables --force
    uv run python -m scripts.prepare_viewables --limit 10
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from sqlalchemy import select

from app.adapters.minio_storage import MinioBlobStorage
from app.adapters.viewers import build_default_registry
from app.core.config import settings
from app.core.db import get_sync_db
from app.models import Document, DocumentStatus
from app.services.viewer_preparation_service import ViewerPreparationService

logger = logging.getLogger(__name__)


@dataclass
class RunStats:
    prepared: int = 0
    skipped_already_prepped: int = 0
    skipped_dry_run: int = 0
    failed: int = 0

    def summary(self) -> str:
        return (
            f"prepared={self.prepared} "
            f"skipped_already_prepped={self.skipped_already_prepped} "
            f"skipped_dry_run={self.skipped_dry_run} "
            f"failed={self.failed}"
        )


def backfill(*, dry_run: bool, force: bool, limit: int | None) -> RunStats:
    storage = MinioBlobStorage(
        endpoint=settings.storage_endpoint,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        bucket=settings.storage_bucket,
        region=settings.storage_region,
    )
    registry = build_default_registry()
    stats = RunStats()

    # One session for the SELECT, a fresh per-doc session for each
    # prep (mirrors the worker's pattern — keeps commits small and
    # stops a single failure from poisoning the batch).
    with get_sync_db() as session:
        query = select(Document).where(Document.status == DocumentStatus.READY)
        if not force:
            query = query.where(Document.viewable_kind.is_(None))
        if limit is not None:
            query = query.limit(limit)
        docs = list(session.execute(query).scalars().all())

    logger.info(
        "found %d READY document(s) to %s",
        len(docs),
        "re-prepare" if force else "prepare",
    )

    for idx, doc in enumerate(docs, 1):
        tag = f"[{idx}/{len(docs)}] {doc.filename} (mime={doc.mime_type})"

        if not force and doc.viewable_kind is not None:
            # Belt-and-braces in case something slipped past the SELECT
            # filter (race with a new upload).
            logger.info("%s already prepared — skip", tag)
            stats.skipped_already_prepped += 1
            continue

        if dry_run:
            logger.info("%s would prepare", tag)
            stats.skipped_dry_run += 1
            continue

        session = get_sync_db()
        try:
            service = ViewerPreparationService(
                session=session,
                registry=registry,
                storage_get=storage.get_sync,
                storage_put=storage.put_sync,
            )
            before = (doc.viewable_kind, doc.viewable_key)
            service.prepare(doc.id)

            # The service commits on success and leaves columns alone on
            # failure; re-read to decide which bucket this doc landed in.
            refreshed = session.execute(
                select(Document.viewable_kind, Document.viewable_key).where(
                    Document.id == doc.id
                )
            ).one()
            after = (refreshed.viewable_kind, refreshed.viewable_key)

            if after != before and after[0] is not None:
                logger.info("%s -> kind=%s key=%s", tag, after[0], after[1])
                stats.prepared += 1
            else:
                # Prep swallowed the error; logs from the service already
                # captured the reason. Count as failed so operators see
                # a non-zero tally at the end.
                logger.warning("%s prep did not populate viewable columns", tag)
                stats.failed += 1
        except Exception:
            # The service is supposed to swallow, but defence in depth:
            # never let one doc kill the whole backfill.
            logger.exception("%s unexpected error", tag)
            stats.failed += 1
        finally:
            session.close()

    return stats


def main() -> int:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log intended work without touching MinIO or the DB.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Re-prepare every READY doc, even those whose viewable "
            "columns are already set. Useful after a provider-logic "
            "change. Safe to re-run; prep is idempotent."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N documents (for smoke testing).",
    )
    args = parser.parse_args()

    stats = backfill(dry_run=args.dry_run, force=args.force, limit=args.limit)
    logger.info("done — %s", stats.summary())
    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
