"""Delete every document (DB row + storage blob + all Chroma collections).

Destructive. Requires --yes to fire. Intended for dev resets and for
recovering from a model-swap that left orphan collections behind.

Usage (from backend/):
    uv run python -m scripts.nuke_documents --yes
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import chromadb
from sqlalchemy import select

from app.adapters.chroma_store import ChromaVectorStore
from app.adapters.embeddings.registry import get_embedding_provider
from app.adapters.minio_storage import MinioBlobStorage
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Document
from app.repositories.document import DocumentRepository

logger = logging.getLogger(__name__)


async def nuke() -> None:
    embedder = get_embedding_provider(settings)
    vector_store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        embedder=embedder,
    )
    storage = MinioBlobStorage(
        endpoint=settings.storage_endpoint,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        bucket=settings.storage_bucket,
        region=settings.storage_region,
    )

    async with SessionLocal() as session:
        docs = (await session.execute(select(Document))).scalars().all()
        logger.info("found %d documents to delete", len(docs))

        repo = DocumentRepository(session)
        for i, doc in enumerate(docs, 1):
            try:
                await storage.delete(doc.storage_key)
            except Exception:
                logger.warning("storage delete failed for %s", doc.id)
            try:
                vector_store.delete(str(doc.id))
            except Exception:
                logger.warning("chunk vector delete failed for %s", doc.id)
            try:
                vector_store.delete_document_vector(str(doc.id))
            except Exception:
                logger.warning("doc-level vector delete failed for %s", doc.id)
            await repo.delete(doc)
            logger.info("[%d/%d] deleted %s", i, len(docs), doc.filename)

        await session.commit()

    # Drop every documents_* Chroma collection, including orphans from
    # prior embedding models. Current-model collections are empty after
    # the loop above; drop them too for a clean slate.
    client = chromadb.HttpClient(
        host=settings.chroma_host, port=settings.chroma_port
    )
    for c in client.list_collections():
        # Catch every vintage of the name: current per-model form
        # (``documents_<slug>``, ``documents_whole_<slug>``) plus the
        # legacy unsuffixed ``documents`` collection from before per-
        # model naming shipped.
        if c.name == "documents" or c.name.startswith("documents_"):
            client.delete_collection(c.name)
            logger.info("dropped chroma collection %s", c.name)

    logger.info("done — storage, DB, and all document collections cleared")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm you want to delete every document and vector",
    )
    args = parser.parse_args()
    if not args.yes:
        print(
            "This will permanently delete every document, its storage "
            "blob, and every documents_* Chroma collection.",
            file=sys.stderr,
        )
        print("Re-run with --yes to confirm.", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(nuke())


if __name__ == "__main__":
    main()
