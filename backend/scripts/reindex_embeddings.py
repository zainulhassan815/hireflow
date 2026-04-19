"""Rebuild the Chroma embedding index for every READY document.

Run this after:
  * Changing ``embedding_provider`` or ``embedding_model`` in settings.
  * Changing the chunking strategy.
  * Corrupted-state recovery where Chroma and Postgres have drifted.

Per-model collection naming means old vectors stay around in a separate
collection; this script only rebuilds the collection for the *currently
configured* model. Orphan collections can be cleaned up manually via
``chroma`` CLI when needed.

Usage (from backend/):
    uv run python -m scripts.reindex_embeddings
    uv run python -m scripts.reindex_embeddings --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from app.adapters.chroma_store import ChromaVectorStore
from app.adapters.embeddings.registry import get_embedding_provider
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Document, DocumentStatus
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


async def reindex(dry_run: bool = False) -> None:
    embedder = get_embedding_provider(settings)
    logger.info(
        "embedding model: %s (will materialise on first embed call)",
        embedder.model_name,
    )

    store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        embedder=embedder,
    )
    logger.info("chroma collection: %s", store.collection_name)

    # Drop both collections so re-indexing starts clean. The per-model
    # naming means we're not nuking other models' data.
    if not dry_run:
        for collection_name in (store.collection_name, store.whole_collection_name):
            try:
                store._client.delete_collection(collection_name)
                logger.info("deleted collection %s", collection_name)
            except Exception:
                logger.info("collection %s did not exist; continuing", collection_name)
        # Re-create with a fresh handle so subsequent upserts target the
        # newly-created collections (chunk + whole-doc).
        store = ChromaVectorStore(
            host=settings.chroma_host,
            port=settings.chroma_port,
            embedder=embedder,
        )

    # F89.c — feed the same store instance into both VectorStore and
    # DocumentSimilarityStore slots so the reindex loop populates both
    # chunk and doc-level collections in one pass.
    indexing = EmbeddingService(store, embedder, similarity_store=store)

    async with SessionLocal() as session:
        # Eagerly load elements via the relationship so we can index
        # outside the session.
        result = await session.execute(
            select(Document).where(Document.status == DocumentStatus.READY)
        )
        docs = result.scalars().all()
        # Materialise elements per doc (awaited inside the session).
        doc_pairs: list[tuple[Document, list]] = []
        for d in docs:
            _ = list(d.elements)  # trigger lazy load
            doc_pairs.append((d, d.elements))

    logger.info("re-indexing %d READY documents", len(doc_pairs))

    for i, (doc, _elements) in enumerate(doc_pairs, 1):
        if not doc.extracted_text:
            logger.info("[%d/%d] skip %s (no text)", i, len(doc_pairs), doc.filename)
            continue
        if not doc.elements:
            logger.warning(
                "[%d/%d] %s has no persisted elements — re-upload or re-extract"
                " to repopulate document_elements (F82.d)",
                i,
                len(doc_pairs),
                doc.filename,
            )
            continue
        if dry_run:
            logger.info("[%d/%d] would re-index %s", i, len(doc_pairs), doc.filename)
            continue
        indexing.index_document(doc)
        logger.info("[%d/%d] re-indexed %s", i, len(doc_pairs), doc.filename)

    logger.info("done")


def main() -> int:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without touching Chroma.",
    )
    args = parser.parse_args()
    asyncio.run(reindex(dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
