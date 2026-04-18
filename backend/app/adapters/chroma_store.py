"""ChromaDB vector store adapter.

Uses ChromaDB's HTTP client to talk to the ChromaDB server running in Docker.
Embedding is handled server-side by ChromaDB's default model (all-MiniLM-L6-v2)
so no local embedding library is needed.
"""

from __future__ import annotations

import logging
from typing import Any

import chromadb

from app.adapters.protocols import VectorHit

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "documents"


class ChromaVectorStore:
    """`VectorStore` protocol implementation backed by ChromaDB."""

    def __init__(self, *, host: str, port: int) -> None:
        self._client = chromadb.HttpClient(host=host, port=port)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self,
        document_id: str,
        chunks: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not chunks:
            return

        # Delete existing chunks for this document first (clean re-index)
        self._delete_by_document_id(document_id)

        ids = [f"{document_id}:{i}" for i in range(len(chunks))]
        enriched_metadatas = [
            {**meta, "document_id": document_id, "chunk_index": i}
            for i, meta in enumerate(metadatas)
        ]

        # ChromaDB has a batch limit; chunk in groups of 500
        batch_size = 500
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            self._collection.add(
                ids=ids[start:end],
                documents=chunks[start:end],
                metadatas=enriched_metadatas[start:end],
            )

        logger.info("indexed %d chunks for document %s", len(chunks), document_id)

    def delete(self, document_id: str) -> None:
        self._delete_by_document_id(document_id)
        logger.info("deleted chunks for document %s", document_id)

    def query(
        self,
        query_text: str,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        kwargs: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": n_results,
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        hits: list[VectorHit] = []
        if not results["ids"] or not results["ids"][0]:
            return hits

        for chunk_id, doc_text, metadata, distance in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
            strict=True,
        ):
            hits.append(
                VectorHit(
                    chunk_id=chunk_id,
                    document_id=metadata.get("document_id", ""),
                    text=doc_text,
                    metadata=metadata,
                    distance=distance,
                )
            )

        return hits

    def _delete_by_document_id(self, document_id: str) -> None:
        try:
            self._collection.delete(where={"document_id": document_id})
        except Exception:
            # Logged but not re-raised: re-indexing should still attempt
            # to add the new chunks. If Chroma is genuinely down the
            # subsequent .add() will surface the error.
            logger.warning(
                "failed to delete existing chunks for document %s",
                document_id,
                exc_info=True,
            )
