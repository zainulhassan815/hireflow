"""ChromaDB vector store adapter.

Uses ChromaDB's HTTP client to talk to the ChromaDB server running in
Docker. Embeddings are computed in our process (not on the Chroma
server) via the injected ``EmbeddingProvider`` — F85.a made this
swappable so we can A/B different models without touching the rest of
the system.

The collection name is suffixed with the model and dimension so two
embedding models can coexist without clashing. A startup-time consistency
check on collection metadata is intentionally not implemented: the
collection name itself encodes the contract.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import chromadb

from app.adapters.protocols import EmbeddingProvider, SimilarDocumentHit, VectorHit
from app.domain.exceptions import DocumentNotIndexed

logger = logging.getLogger(__name__)

_COLLECTION_PREFIX = "documents"
_WHOLE_COLLECTION_PREFIX = "documents_whole"


def _safe_collection_suffix(model_name: str) -> str:
    """Reduce ``BAAI/bge-small-en-v1.5`` to ``bge_small_en_v1_5`` so it's
    a valid Chroma collection name (alphanumerics, ``_``, ``-``, no slashes)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", model_name.split("/")[-1]).strip("_-")


class ChromaVectorStore:
    """``VectorStore`` protocol implementation backed by ChromaDB.

    Takes an ``EmbeddingProvider`` so the model is owned by us, not by
    Chroma. Vectors are pre-computed and passed via ``embeddings=`` /
    ``query_embeddings=`` — Chroma's bundled embedding function is
    never invoked.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        embedder: EmbeddingProvider,
    ) -> None:
        self._client = chromadb.HttpClient(host=host, port=port)
        self._embedder = embedder
        # Per-model collection isolates vectors of incompatible dimensions
        # and lets two models coexist while we A/B them. Switching model
        # = a new collection; old one stays around until manually dropped
        # (see scripts/reindex_embeddings.py).
        model_slug = _safe_collection_suffix(embedder.model_name)
        self._collection_name = f"{_COLLECTION_PREFIX}_{model_slug}"
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": embedder.model_name,
            },
        )

        # F89.c: second, separate collection holds one mean-pooled vector
        # per document. Kept isolated from the chunk collection so chunk
        # queries never surface doc-level rows (and vice versa) — no
        # post-filter plumbing needed on either path.
        self._whole_collection_name = f"{_WHOLE_COLLECTION_PREFIX}_{model_slug}"
        self._whole_collection = self._client.get_or_create_collection(
            name=self._whole_collection_name,
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": embedder.model_name,
            },
        )

        self._log_startup_integrity()

    @property
    def collection_name(self) -> str:
        return self._collection_name

    @property
    def whole_collection_name(self) -> str:
        return self._whole_collection_name

    @property
    def embedder(self) -> EmbeddingProvider:
        """Public handle to the embedder this store was built with.

        Lets ``SearchService`` ask for the embedder's recommended
        distance threshold (F85.d) without poking at a private attr.
        """
        return self._embedder

    def _log_startup_integrity(self) -> None:
        """F85.f: loud log line + mismatch warning on construction.

        Per-model collection naming means two different models can't
        *share* a collection (they each land in their own). This check
        mostly catches the "someone attached unusual metadata to our
        named collection" drift and gives operators a snapshot of
        model / dim / chunk count when the worker or API boots.
        """
        try:
            existing_meta = self._collection.metadata or {}
            stored_model = existing_meta.get("embedding_model")
            count = self._collection.count()
            whole_count = self._whole_collection.count()
            logger.info(
                "ChromaVectorStore ready: collection=%s model=%s chunks=%d "
                "whole-doc-collection=%s documents=%d",
                self._collection_name,
                self._embedder.model_name,
                count,
                self._whole_collection_name,
                whole_count,
            )
            if stored_model and stored_model != self._embedder.model_name:
                logger.warning(
                    "Chroma collection %s metadata says embedding_model=%r "
                    "but we were instantiated with %r. Run "
                    "scripts/reindex_embeddings.py to align.",
                    self._collection_name,
                    stored_model,
                    self._embedder.model_name,
                )
        except Exception:
            # Never let a diagnostics log crash the process at boot.
            logger.warning(
                "ChromaVectorStore: integrity log failed (non-fatal)",
                exc_info=True,
            )

    def upsert(
        self,
        document_id: str,
        chunks: list[str],
        metadatas: list[dict[str, Any]],
        *,
        embedding_texts: list[str] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """Upsert chunks into the collection.

        ``chunks`` is what Chroma stores as the ``documents`` field
        (used for snippet display and highlight tokenization).

        ``embedding_texts`` (optional) is what gets passed to the
        embedder. When None, we embed ``chunks`` directly. When set,
        the store embeds ``embedding_texts`` but still stores
        ``chunks`` as the displayable document field — this separation
        powers contextual retrieval (F82.c): context+chunk feeds the
        vector while plain chunk text stays clean for snippets.

        ``embeddings`` (F89.c) lets a caller pre-compute vectors
        externally and supply them directly — the same vectors can then
        be reused (e.g. mean-pooled into a doc-level representation)
        without a second embedding pass.
        """
        if not chunks:
            return

        # Delete existing chunks for this document first (clean re-index)
        self._delete_by_document_id(document_id)

        ids = [f"{document_id}:{i}" for i in range(len(chunks))]
        enriched_metadatas = [
            {**meta, "document_id": document_id, "chunk_index": i}
            for i, meta in enumerate(metadatas)
        ]

        if embeddings is None:
            to_embed = embedding_texts if embedding_texts is not None else chunks
            embeddings = self._embedder.embed_documents(to_embed)
        elif len(embeddings) != len(chunks):
            raise ValueError(
                f"Pre-computed embeddings length ({len(embeddings)}) does not "
                f"match chunks length ({len(chunks)})."
            )

        # ChromaDB has a batch limit; chunk in groups of 500
        batch_size = 500
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            self._collection.add(
                ids=ids[start:end],
                documents=chunks[start:end],
                metadatas=enriched_metadatas[start:end],
                embeddings=embeddings[start:end],
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
        query_embedding = self._embedder.embed_query(query_text)

        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
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

    # ---- DocumentSimilarityStore (F89.c) -----------------------------------

    def upsert_document_vector(
        self,
        document_id: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> None:
        """Replace the doc-level vector for ``document_id``.

        One vector per document, keyed by ``document_id`` — same value
        in both the id slot and the metadata slot so metadata-based
        ``where`` filters (owner scoping) and id-based lookups both
        work. Chroma's ``upsert`` overwrites an existing id, which is
        the behaviour we want on re-index.
        """
        self._whole_collection.upsert(
            ids=[document_id],
            embeddings=[embedding],
            metadatas=[metadata],
        )

    def delete_document_vector(self, document_id: str) -> None:
        """Remove the doc-level vector for ``document_id`` (no-op if absent)."""
        try:
            self._whole_collection.delete(ids=[document_id])
        except Exception:
            logger.warning(
                "failed to delete doc-level vector for document %s",
                document_id,
                exc_info=True,
            )

    def find_similar_documents(
        self,
        source_document_id: str,
        n_results: int,
        where: dict[str, Any] | None = None,
    ) -> list[SimilarDocumentHit]:
        """Return the nearest neighbours of ``source_document_id``.

        Fetches the source document's stored vector first, then queries
        the whole-doc collection with it. Raising
        ``DocumentNotIndexed`` when the source has no vector is how we
        distinguish "doc exists but isn't in the similarity index yet"
        from "no results" — the caller's HTTP translation differs.
        """
        source = self._whole_collection.get(
            ids=[source_document_id],
            include=["embeddings"],
        )
        # Chroma returns either ``None``, an empty list/array, or a list
        # (or numpy ndarray) of vectors. Normalise via ``len``; `or []`
        # doesn't work because a populated numpy array makes the boolean
        # check ambiguous.
        raw = source.get("embeddings")
        if raw is None or len(raw) == 0:
            raise DocumentNotIndexed(
                "Document is not indexed in the similarity store. "
                "Re-upload or run scripts/reindex_embeddings.py."
            )
        source_vector = list(raw[0])

        kwargs: dict[str, Any] = {
            "query_embeddings": [source_vector],
            "n_results": n_results,
        }
        if where:
            kwargs["where"] = where

        results = self._whole_collection.query(**kwargs)
        if not results["ids"] or not results["ids"][0]:
            return []

        hits: list[SimilarDocumentHit] = []
        for doc_id, metadata, distance in zip(
            results["ids"][0],
            results["metadatas"][0],
            results["distances"][0],
            strict=True,
        ):
            hits.append(
                SimilarDocumentHit(
                    document_id=doc_id,
                    distance=distance,
                    metadata=metadata or {},
                )
            )
        return hits
