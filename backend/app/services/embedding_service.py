"""Document embedding orchestration.

Given a document and its pre-built chunks (element-aware, optionally
contextualized), upserts vectors + per-chunk metadata into the vector
store. Callers are the Celery extraction pipeline and the
``reindex_embeddings`` script.
"""

from __future__ import annotations

import logging
from typing import Any

from app.adapters.protocols import (
    DocumentSimilarityStore,
    Element,
    EmbeddingProvider,
    VectorStore,
)
from app.models import Document
from app.services.chunking import CHUNKING_VERSION, Chunk, chunk_elements
from app.services.document_vector import pool_document_embedding

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(
        self,
        vector_store: VectorStore,
        embedder: EmbeddingProvider,
        similarity_store: DocumentSimilarityStore | None = None,
    ) -> None:
        self._store = vector_store
        self._embedder = embedder
        self._similarity_store = similarity_store

    def index_document(
        self,
        doc: Document,
        *,
        chunks: list[Chunk] | None = None,
        elements: list[Element] | None = None,
    ) -> None:
        """Embed and upsert chunks.

        Two call-sites:

        * ``ExtractionService`` passes ``chunks`` (already
          contextualized by the pipeline) — preferred path.
        * ``scripts/reindex_embeddings.py`` passes ``elements`` when
          only re-embedding existing docs (no contextualization).

        If both are passed, ``chunks`` wins. If neither is passed, we
        load elements from the persisted ``document_elements`` rows on
        the Document relationship.
        """
        resolved_chunks = chunks
        if resolved_chunks is None:
            resolved_elements = (
                elements if elements is not None else _load_elements(doc)
            )
            if not resolved_elements:
                logger.info("document %s has no elements, skipping indexing", doc.id)
                return
            resolved_chunks = chunk_elements(resolved_elements)

        if not resolved_chunks:
            logger.info("document %s chunked to zero, skipping indexing", doc.id)
            return

        texts_for_embedding = [_text_for_embedding(c) for c in resolved_chunks]
        texts_for_display = [c.text for c in resolved_chunks]
        metadatas = self._build_metadatas(doc, resolved_chunks)

        # F89.c — embed once in the service layer so we can reuse the
        # vectors for doc-level mean-pooling without a second pass
        # through the embedder. Pre-F89 the store embedded internally.
        embeddings = self._embedder.embed_documents(texts_for_embedding)

        self._store.upsert(
            str(doc.id),
            texts_for_display,
            metadatas,
            embedding_texts=texts_for_embedding,
            embeddings=embeddings,
        )

        # F89.c — doc-level vector: mean-pool the chunk embeddings
        # (already on the unit sphere per chunk) and store one vector
        # per document in the separate similarity collection. Skipped
        # when the similarity store isn't wired (legacy test paths).
        if self._similarity_store is not None:
            pooled = pool_document_embedding(embeddings)
            doc_metadata: dict[str, Any] = {
                "document_id": str(doc.id),
                "owner_id": str(doc.owner_id),
            }
            if doc.document_type is not None:
                doc_metadata["document_type"] = doc.document_type.value
            self._similarity_store.upsert_document_vector(
                str(doc.id),
                pooled,
                doc_metadata,
            )

        # Stamp versions so a later targeted re-embed can find docs
        # with a stale model / pipeline version.
        doc.chunking_version = CHUNKING_VERSION
        doc.embedding_model_version = self._embedder.model_name

        contextualized = sum(1 for c in resolved_chunks if c.context)
        logger.info(
            "indexed document %s (%d chunks, %d contextualized, chunking=%s)",
            doc.id,
            len(resolved_chunks),
            contextualized,
            CHUNKING_VERSION,
        )

    def remove_document(self, document_id: str) -> None:
        """Remove all chunks + the doc-level vector for a document."""
        self._store.delete(document_id)
        if self._similarity_store is not None:
            self._similarity_store.delete_document_vector(document_id)

    @staticmethod
    def _build_metadatas(doc: Document, chunks: list[Chunk]) -> list[dict[str, Any]]:
        """One metadata dict per chunk.

        Doc-level fields (filename, owner, etc.) are repeated on every
        chunk because Chroma filters only look at chunk-level metadata.
        Chunk-level fields (section_heading, page_number, element_kinds,
        context) carry the structure- and F82.c signal.
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
                "has_context": chunk.context is not None,
            }
            if chunk.context:
                meta["context"] = chunk.context

            for key, value in chunk.metadata.items():
                if value is None:
                    continue
                if isinstance(value, list):
                    meta[key] = ", ".join(str(v) for v in value)
                else:
                    meta[key] = value
            out.append(meta)
        return out


def _text_for_embedding(chunk: Chunk) -> str:
    """Return the text that actually goes into the embedding model.

    If the chunk has context, prepend it; otherwise plain chunk text.
    Display-side (snippets, highlights) uses ``chunk.text`` only, so
    the context doesn't leak into the UI.
    """
    if chunk.context:
        return f"{chunk.context}\n\n{chunk.text}"
    return chunk.text


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
