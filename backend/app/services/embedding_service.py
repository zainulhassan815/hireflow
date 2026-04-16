"""Document embedding orchestration.

Chunks extracted text and indexes it in the vector store. Called from the
Celery extraction pipeline after classification completes.
"""

from __future__ import annotations

import logging
from typing import Any

from app.adapters.protocols import VectorStore
from app.models import Document
from app.services.chunking import chunk_text

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, vector_store: VectorStore) -> None:
        self._store = vector_store

    def index_document(self, doc: Document) -> None:
        """Chunk the document's extracted text and upsert into the vector store."""
        if not doc.extracted_text or not doc.extracted_text.strip():
            logger.info("document %s has no text, skipping indexing", doc.id)
            return

        chunks = chunk_text(doc.extracted_text)
        if not chunks:
            return

        metadatas = self._build_metadatas(doc, len(chunks))
        self._store.upsert(str(doc.id), chunks, metadatas)

        logger.info("indexed document %s (%d chunks)", doc.id, len(chunks))

    def remove_document(self, document_id: str) -> None:
        """Remove all chunks for a document from the vector store."""
        self._store.delete(document_id)

    @staticmethod
    def _build_metadatas(doc: Document, chunk_count: int) -> list[dict[str, Any]]:
        """Build per-chunk metadata for filtering during search."""
        base: dict[str, Any] = {
            "filename": doc.filename,
            "mime_type": doc.mime_type,
            "owner_id": str(doc.owner_id),
        }

        if doc.document_type:
            base["document_type"] = doc.document_type.value

        doc_meta = doc.metadata_ or {}
        if "skills" in doc_meta:
            base["skills"] = ", ".join(doc_meta["skills"])
        if "experience_years" in doc_meta:
            base["experience_years"] = doc_meta["experience_years"]

        return [
            {**base, "chunk_index": i, "total_chunks": chunk_count}
            for i in range(chunk_count)
        ]
