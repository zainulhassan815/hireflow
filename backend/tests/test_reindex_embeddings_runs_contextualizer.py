"""F103.d — regression cover for the bug F103.d fixed: pre-F103.d
``reindex_embeddings.py`` invoked ``EmbeddingService.index_document``
without passing ``chunks=``, falling through to plain ``chunk_elements``
without contextualization. The result was strictly-worse vectors than
fresh ingestion.

This test verifies the script now invokes the contextualizer once per
doc with elements. Without it, future maintenance could re-break the
wiring (e.g., reverting the `chunks=` argument) without any test
coverage tripping.

We patch ``get_contextualizer`` to return a recorder so the test
doesn't need a real LLM, and stub the embedding/Chroma layer to keep
the test offline.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.db import sync_engine
from app.models import Document, DocumentElement, DocumentStatus, DocumentType
from app.services.chunking import Chunk


class _RecordingContextualizer:
    """Captures every ``contextualize`` call; passes chunks through."""

    model_name = "recorder"

    def __init__(self) -> None:
        self.calls: list[tuple[Document, int]] = []

    def contextualize(self, document: Document, chunks: list[Chunk]) -> list[Chunk]:
        self.calls.append((document, len(chunks)))
        return chunks


class _DummyVectorStore:
    """Just enough surface for the reindex script's drop-and-recreate +
    upsert calls. Records nothing; the test only cares about the
    contextualizer being invoked."""

    def __init__(self) -> None:
        self.collection_name = "test-chunk"
        self.whole_collection_name = "test-whole"

        class _Client:
            def delete_collection(self, name: str) -> None:
                raise Exception("not present")

        self._client = _Client()

    def upsert(self, *_: Any, **__: Any) -> None:
        return None

    def delete(self, *_: Any, **__: Any) -> None:
        return None

    def upsert_document_vector(self, *_: Any, **__: Any) -> None:
        return None

    def delete_document_vector(self, *_: Any, **__: Any) -> None:
        return None


class _DummyEmbedder:
    model_name = "test-embedder"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 4 for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * 4


@pytest.mark.asyncio
async def test_reindex_invokes_contextualizer_for_each_doc(admin_user) -> None:
    """Seed two READY docs with elements, run the script, assert
    the contextualizer was called for each."""
    with Session(sync_engine) as session:
        for filename in ("alice.pdf", "bob.pdf"):
            doc = Document(
                owner_id=admin_user.id,
                filename=filename,
                mime_type="application/pdf",
                size_bytes=100,
                storage_key=f"key-{uuid4()}",
                status=DocumentStatus.READY,
                document_type=DocumentType.RESUME,
                extracted_text="some body text",
                metadata_={},
            )
            doc.elements.append(
                DocumentElement(
                    kind="NarrativeText",
                    text="some body text",
                    page_number=1,
                    order_index=0,
                    metadata_={},
                )
            )
            session.add(doc)
        session.commit()

    recorder = _RecordingContextualizer()

    # Patch the registry getters so the script picks up our recorders.
    # The test runs the async ``reindex`` directly rather than via
    # subprocess so the recorder stays observable.
    from scripts import reindex_embeddings

    with (
        patch.object(reindex_embeddings, "get_contextualizer", return_value=recorder),
        patch.object(
            reindex_embeddings, "get_embedding_provider", return_value=_DummyEmbedder()
        ),
        patch.object(
            reindex_embeddings, "ChromaVectorStore", return_value=_DummyVectorStore()
        ),
    ):
        await reindex_embeddings.reindex(dry_run=False)

    # Each seeded doc should have triggered a contextualizer call.
    filenames_called = [doc.filename for doc, _n in recorder.calls]
    assert sorted(filenames_called) == ["alice.pdf", "bob.pdf"]
    # Each call should have at least one chunk.
    assert all(n >= 1 for _doc, n in recorder.calls)


@pytest.mark.asyncio
async def test_reindex_persists_version_stamps(admin_user) -> None:
    """Per-F103.d: the contextualizer's metadata stamp + the embedding
    service's chunking/embedding versions must flush to Postgres.
    Pre-F103.d the script loaded docs in one session, mutated detached
    instances, and silently lost version stamps — this regresses
    against that bug."""
    from app.core.db import SessionLocal as AsyncSessionLocal

    with Session(sync_engine) as session:
        doc = Document(
            owner_id=admin_user.id,
            filename="alice.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            storage_key=f"key-{uuid4()}",
            status=DocumentStatus.READY,
            document_type=DocumentType.RESUME,
            extracted_text="some body text",
            metadata_={},
        )
        doc.elements.append(
            DocumentElement(
                kind="NarrativeText",
                text="some body text",
                page_number=1,
                order_index=0,
                metadata_={},
            )
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id

    class _StampingContextualizer:
        """Mimics the LLM contextualizer's stamp behaviour without LLM calls."""

        model_name = "stamp"

        def contextualize(self, document, chunks):
            document.metadata_ = {
                **(document.metadata_ or {}),
                "contextualization_version": "v2-haiku-entity-aware",
            }
            return chunks

    from scripts import reindex_embeddings

    with (
        patch.object(
            reindex_embeddings,
            "get_contextualizer",
            return_value=_StampingContextualizer(),
        ),
        patch.object(
            reindex_embeddings,
            "get_embedding_provider",
            return_value=_DummyEmbedder(),
        ),
        patch.object(
            reindex_embeddings, "ChromaVectorStore", return_value=_DummyVectorStore()
        ),
    ):
        await reindex_embeddings.reindex(dry_run=False)

    # Re-fetch from a fresh async session to verify the stamp was
    # actually flushed to Postgres.
    async with AsyncSessionLocal() as session:
        persisted = await session.get(Document, doc_id)
        assert persisted.metadata_ is not None
        assert (
            persisted.metadata_.get("contextualization_version")
            == "v2-haiku-entity-aware"
        )


@pytest.mark.asyncio
async def test_reindex_dry_run_skips_contextualizer(admin_user) -> None:
    """``--dry-run`` should not call the contextualizer (would burn LLM
    cost for no reason)."""
    with Session(sync_engine) as session:
        doc = Document(
            owner_id=admin_user.id,
            filename="alice.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            storage_key=f"key-{uuid4()}",
            status=DocumentStatus.READY,
            document_type=DocumentType.RESUME,
            extracted_text="some body text",
            metadata_={},
        )
        doc.elements.append(
            DocumentElement(
                kind="NarrativeText",
                text="some body text",
                page_number=1,
                order_index=0,
                metadata_={},
            )
        )
        session.add(doc)
        session.commit()

    recorder = _RecordingContextualizer()

    from scripts import reindex_embeddings

    with (
        patch.object(reindex_embeddings, "get_contextualizer", return_value=recorder),
        patch.object(
            reindex_embeddings, "get_embedding_provider", return_value=_DummyEmbedder()
        ),
        patch.object(
            reindex_embeddings, "ChromaVectorStore", return_value=_DummyVectorStore()
        ),
    ):
        await reindex_embeddings.reindex(dry_run=True)

    # Dry run should not have called the contextualizer.
    assert recorder.calls == []
