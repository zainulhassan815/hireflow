"""Rebuild the Chroma embedding index for every READY document.

Run this after:
  * Changing ``embedding_provider`` or ``embedding_model`` in settings.
  * Changing the chunking strategy.
  * Bumping ``CONTEXTUALIZATION_VERSION`` (F103.d).
  * Corrupted-state recovery where Chroma and Postgres have drifted
    (orphan vectors from prior DB states).

Per-model collection naming means old vectors stay around in a separate
collection; this script only rebuilds the collection for the *currently
configured* model. Orphan collections can be cleaned up manually via
``chroma`` CLI when needed.

F103.d: the script now invokes the contextualizer (via the same
registry the worker uses). Pre-F103.d the re-embed silently skipped
contextualization, producing strictly-worse vectors than fresh
ingestion.

Usage (from backend/):
    uv run python -m scripts.reindex_embeddings
    uv run python -m scripts.reindex_embeddings --dry-run
    uv run python -m scripts.reindex_embeddings --inspect <doc_id>
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from uuid import UUID

from sqlalchemy import select

from app.adapters.chroma_store import ChromaVectorStore
from app.adapters.contextualizers.registry import get_contextualizer
from app.adapters.embeddings.registry import get_embedding_provider
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Document, DocumentStatus
from app.services.chunking import chunk_elements
from app.services.embedding_service import EmbeddingService, elements_from_orm

logger = logging.getLogger(__name__)


async def reindex(dry_run: bool = False) -> None:
    embedder = get_embedding_provider(settings)
    logger.info(
        "embedding model: %s (will materialise on first embed call)",
        embedder.model_name,
    )

    contextualizer = get_contextualizer(settings)
    logger.info("contextualizer model: %s", contextualizer.model_name)

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
        result = await session.execute(
            select(Document.id).where(Document.status == DocumentStatus.READY)
        )
        doc_ids = [row[0] for row in result.all()]

    logger.info("re-indexing %d READY documents", len(doc_ids))

    # Per-doc session so the contextualizer's metadata stamp + the
    # embedding service's ``chunking_version`` / ``embedding_model_version``
    # stamps actually flush to Postgres. Pre-F103.d the script loaded
    # docs in one session, exited the session, then mutated detached
    # instances — version stamps were silently lost. Re-attach + commit
    # per doc so each iteration is self-contained.
    for i, doc_id in enumerate(doc_ids, 1):
        async with SessionLocal() as session:
            doc = await session.get(Document, doc_id)
            if doc is None:
                continue
            # Trigger lazy load of elements inside this session.
            _ = list(doc.elements)

            if not doc.extracted_text:
                logger.info(
                    "[%d/%d] skip %s (no text)", i, len(doc_ids), doc.filename
                )
                continue
            if not doc.elements:
                logger.warning(
                    "[%d/%d] %s has no persisted elements — re-upload or "
                    "re-extract to repopulate document_elements (F82.d)",
                    i,
                    len(doc_ids),
                    doc.filename,
                )
                continue
            if dry_run:
                logger.info(
                    "[%d/%d] would re-index %s", i, len(doc_ids), doc.filename
                )
                continue

            # F103.d — run the contextualizer; pre-F103.d the script
            # silently skipped this and produced uncontextualized vectors.
            chunks = chunk_elements(elements_from_orm(doc.elements))
            chunks = contextualizer.contextualize(doc, chunks)
            indexing.index_document(doc, chunks=chunks)
            await session.commit()
            logger.info("[%d/%d] re-indexed %s", i, len(doc_ids), doc.filename)

    logger.info("done")


async def inspect(document_id: UUID) -> None:
    """Dump the first chunk's contextualized text for a single doc.

    Operator tool — runs the contextualizer on one doc without writing
    to Chroma. Useful for eyeballing the F103.d prompt's output before
    committing to a full re-embed.
    """
    contextualizer = get_contextualizer(settings)
    async with SessionLocal() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            logger.error("document %s not found", document_id)
            return
        if not doc.elements:
            logger.error("document %s has no persisted elements", document_id)
            return
        elements = elements_from_orm(doc.elements)

    chunks = chunk_elements(elements)
    if not chunks:
        logger.error("document %s chunked to zero", document_id)
        return

    contextualized = contextualizer.contextualize(doc, chunks)
    first = contextualized[0]
    logger.info("--- inspecting %s (chunk 0) ---", doc.filename)
    logger.info("context:\n%s", first.context or "(no context)")
    logger.info(
        "stamped contextualization_version=%s",
        (doc.metadata_ or {}).get("contextualization_version", "∅"),
    )


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
    parser.add_argument(
        "--inspect",
        metavar="DOC_ID",
        type=UUID,
        default=None,
        help=(
            "Run the contextualizer on one doc and dump the first "
            "chunk's context. No writes."
        ),
    )
    args = parser.parse_args()

    if args.inspect is not None:
        asyncio.run(inspect(args.inspect))
        return 0

    asyncio.run(reindex(dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
