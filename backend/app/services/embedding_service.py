"""Document embedding orchestration.

Chunks the document's typed elements (F82.d output, F82.e chunker) and
upserts vectors + per-chunk metadata into the vector store. Called from
the Celery extraction pipeline after classification.
"""

from __future__ import annotations

import logging
from typing import Any

from app.adapters.protocols import Element, VectorStore
from app.models import Document
from app.services.chunking import CHUNKING_VERSION, Chunk, chunk_elements

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, vector_store: VectorStore) -> None:
        self._store = vector_store

    def index_document(
        self, doc: Document, elements: list[Element] | None = None
    ) -> None:
        """Chunk the document's elements and upsert into the vector store.

        If ``elements`` isn't passed, we load them from the persisted
        ``document_elements`` rows attached to the document (eagerly
        loaded via the relationship). Callers that have the elements in
        memory already (e.g. ``ExtractionService`` right after extract)
        should pass them directly to avoid the extra lookup.
        """
        resolved = elements if elements is not None else _load_elements(doc)
        if not resolved:
            logger.info("document %s has no elements, skipping indexing", doc.id)
            return

        chunks = chunk_elements(resolved)
        if not chunks:
            logger.info("document %s chunked to zero, skipping indexing", doc.id)
            return

        texts = [c.text for c in chunks]
        metadatas = self._build_metadatas(doc, chunks)
        self._store.upsert(str(doc.id), texts, metadatas)

        logger.info(
            "indexed document %s (%d chunks, chunking_version=%s)",
            doc.id,
            len(chunks),
            CHUNKING_VERSION,
        )

    def remove_document(self, document_id: str) -> None:
        """Remove all chunks for a document from the vector store."""
        self._store.delete(document_id)

    @staticmethod
    def _build_metadatas(doc: Document, chunks: list[Chunk]) -> list[dict[str, Any]]:
        """One metadata dict per chunk.

        Doc-level fields (filename, owner, etc.) are repeated on every
        chunk because Chroma filters only look at chunk-level metadata.
        Chunk-level fields (section_heading, page_number, element_kinds)
        carry the structure-aware signal that F82.e provides.
        """
        doc_meta = doc.metadata_ or {}
        base: dict[str, Any] = {
            "filename": doc.filename,
            "mime_type": doc.mime_type,
            "owner_id": str(doc.owner_id),
        }
        if doc.document_type:
            base["document_type"] = doc.document_type.value
        if "skills" in doc_meta:
            base["skills"] = ", ".join(doc_meta["skills"])
        if "experience_years" in doc_meta:
            base["experience_years"] = doc_meta["experience_years"]

        out: list[dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            meta: dict[str, Any] = {
                **base,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "chunking_version": CHUNKING_VERSION,
            }
            # Flatten the chunk metadata into the per-chunk dict. Chroma
            # accepts scalars and lists of scalars; skip anything None
            # so the filter surface stays clean.
            for key, value in chunk.metadata.items():
                if value is None:
                    continue
                if isinstance(value, list):
                    # Chroma prefers scalars; comma-join for display/filter.
                    meta[key] = ", ".join(str(v) for v in value)
                else:
                    meta[key] = value
            out.append(meta)
        return out


def _load_elements(doc: Document) -> list[Element]:
    """Load elements from the ORM relationship and convert to Element dataclass."""
    if not doc.elements:
        return []
    return [
        Element(
            kind=row.kind,
            text=row.text,
            page_number=row.page_number,
            order=row.order_index,
            metadata=row.metadata_ or {},
        )
        for row in doc.elements
    ]
