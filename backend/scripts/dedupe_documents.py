"""Remove duplicate documents and backfill content hashes.

Needed once, to clear damage done before ``content_sha256`` existed: a
Gmail reconnect used to mint a new connection with an empty ingest
ledger, so every message was re-imported and every attachment became a
second document.

Order matters, and it is the reason this is a script rather than a
migration. Duplicates are *defined* by their hash, so nothing can be
deduped until the hashes exist — but writing hashes for a duplicate pair
violates ``UNIQUE (owner_id, content_sha256)`` immediately. So:

  1. read every blob and hash it **in memory only**;
  2. group by (owner, hash) and pick a survivor per group;
  3. delete the losers, with their blobs and vectors;
  4. only then persist hashes, one per group.

A crash between 3 and 4 is safe: hashes stay NULL, the constraint stays
satisfied, and a re-run recomputes from scratch.

The survivor is whichever copy is **referenced** — by
``candidates.source_document_id`` or ``candidate_attachments`` — falling
back to the oldest when nothing references any of them. Picking the
oldest unconditionally looked reasonable and was wrong: on real data the
candidate link sat on a *later* copy, and ``ON DELETE SET NULL`` would
have silently orphaned that candidate.

Usage (from backend/):
    uv run python scripts/dedupe_documents.py            # dry run
    uv run python scripts/dedupe_documents.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
from collections import defaultdict
from uuid import UUID

from sqlalchemy import select, text

from app.api.deps import _blob_storage, _similarity_store, _vector_store
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Document, User
from app.repositories.document import DocumentRepository
from app.services.document_service import DocumentService

logger = logging.getLogger("dedupe")


async def _reference_counts(session, ids: list[UUID]) -> dict[UUID, int]:
    """How many candidate records point at each document.

    A referenced copy must outlive its duplicates: ``source_document_id``
    is ``ON DELETE SET NULL``, so deleting the wrong one severs a
    candidate from the resume it was parsed from, silently.
    """
    if not ids:
        return {}
    rows = await session.execute(
        text(
            "select d.id,"
            " (select count(*) from candidates c where c.source_document_id = d.id)"
            " + (select count(*) from candidate_attachments a where a.document_id = d.id)"
            " as refs"
            " from documents d where d.id = any(:ids)"
        ),
        {"ids": ids},
    )
    return {r[0]: r[1] for r in rows}


def _survivor(members: list[Document], refs: dict[UUID, int]) -> Document:
    """Most-referenced copy, oldest as the tie-break."""
    return max(members, key=lambda d: (refs.get(d.id, 0), -d.created_at.timestamp()))


async def dedupe(*, apply: bool) -> int:
    # Reuse the app's configured client rather than rebuilding it; the
    # secret is a SecretStr and the wiring already handles that.
    storage = _blob_storage

    async with SessionLocal() as session:
        documents = list((await session.execute(select(Document))).scalars().all())

    logger.info("hashing %d documents", len(documents))
    groups: dict[tuple[UUID, str], list[Document]] = defaultdict(list)
    unreadable = 0
    for doc in documents:
        try:
            data = await storage.get(doc.storage_key)
        except Exception:
            # A missing blob cannot be hashed or compared; leave it alone
            # rather than guess whether it duplicates something.
            logger.warning(
                "unreadable blob for %s (%s); skipping", doc.id, doc.filename
            )
            unreadable += 1
            continue
        groups[(doc.owner_id, hashlib.sha256(data).hexdigest())].append(doc)

    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    doomed = sum(len(v) - 1 for v in dupes.values())
    logger.info(
        "%d distinct files, %d duplicate groups, %d documents to remove%s",
        len(groups),
        len(dupes),
        doomed,
        "" if apply else "  (dry run — nothing written)",
    )

    async with SessionLocal() as session:
        refs = await _reference_counts(
            session, [d.id for members in dupes.values() for d in members]
        )

    survivors: dict[tuple[UUID, str], Document] = {}
    for key, members in sorted(dupes.items(), key=lambda kv: -len(kv[1])):
        keep = _survivor(members, refs)
        survivors[key] = keep
        losers = [d for d in members if d.id != keep.id]
        logger.info(
            "  %s  keep %s (%s, %d refs)  drop %d: %s",
            key[1][:12],
            keep.id,
            keep.created_at.date(),
            refs.get(keep.id, 0),
            len(losers),
            ", ".join(d.filename[:28] for d in losers),
        )

    if not apply:
        return 0

    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        # The vector stores are not optional here: without them
        # ``delete`` silently skips Chroma and leaves the deleted
        # documents' vectors behind, where they keep winning retrieval
        # slots and get discarded later as orphans.
        service = DocumentService(
            repo,
            storage,
            max_file_size_bytes=settings.max_file_size_mb * 1024 * 1024,
            vector_store=_vector_store,
            similarity_store=_similarity_store,
        )
        for key, members in dupes.items():
            owner = await session.get(User, key[0])
            keep_id = survivors[key].id
            for loser in members:
                if loser.id != keep_id:
                    await service.delete(loser.id, actor=owner)

    # Only now is every group down to one row, so the unique constraint
    # cannot be violated by these writes.
    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        written = 0
        for key, members in groups.items():
            digest = key[1]
            keep = survivors.get(key) or _survivor(members, refs)
            doc = await session.get(Document, keep.id)
            if doc is None or doc.content_sha256 == digest:
                continue
            doc.content_sha256 = digest
            written += 1
        await session.commit()

    logger.info("removed %d duplicates, hashed %d documents", doomed, written)
    if unreadable:
        logger.warning(
            "%d documents had unreadable blobs and were left alone", unreadable
        )
    return 0


def main() -> int:
    logging.basicConfig(
        format="%(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete duplicates and write hashes. Default is a dry run.",
    )
    args = parser.parse_args()
    return asyncio.run(dedupe(apply=args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
