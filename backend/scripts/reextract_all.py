"""Re-enqueue every document for extraction (F82.d pipeline upgrades).

Use-case: you upgraded the extractor (F82.d) or the chunker (F82.e) and
need existing docs to be re-processed from scratch — including fresh
``document_elements`` rows. Sets each doc's status back to PENDING and
fires the Celery extract task. The worker handles the rest.

Usage:
    uv run python -m scripts.reextract_all
    uv run python -m scripts.reextract_all --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from uuid import UUID

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Document, DocumentStatus

logger = logging.getLogger(__name__)


async def reextract(dry_run: bool = False) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Document).where(
                Document.status.in_(
                    (
                        DocumentStatus.READY,
                        DocumentStatus.FAILED,
                        # Include PROCESSING too — covers worker-crash
                        # leftovers where the task died mid-flight.
                        DocumentStatus.PROCESSING,
                        DocumentStatus.PENDING,
                    )
                )
            )
        )
        docs = result.scalars().all()
        doc_ids: list[UUID] = [d.id for d in docs]

        logger.info("found %d docs to re-extract", len(doc_ids))

        if not dry_run:
            for doc in docs:
                doc.status = DocumentStatus.PENDING
            await session.commit()

    if dry_run:
        for i, doc_id in enumerate(doc_ids, 1):
            logger.info("[%d/%d] would re-extract %s", i, len(doc_ids), doc_id)
        return

    # Enqueue outside the session — Celery task runs in the worker.
    from app.worker.tasks import extract_document_text

    for i, doc_id in enumerate(doc_ids, 1):
        extract_document_text.delay(str(doc_id))
        logger.info("[%d/%d] enqueued %s", i, len(doc_ids), doc_id)

    logger.info("done — worker will process asynchronously")


def main() -> int:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without changing anything.",
    )
    args = parser.parse_args()
    asyncio.run(reextract(dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
