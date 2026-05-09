"""F103.c.2 — ReembedService unit tests.

Worker-side service. Tests use stubs for the LLM-backed
contextualizer and the embedding service so they're fast and
deterministic. The end-to-end Chroma+LLM path is exercised by
the F103.d existing tests.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.adapters.contextualizers.llm import CONTEXTUALIZATION_VERSION
from app.core.db import sync_engine
from app.models import Document, DocumentElement, DocumentStatus, DocumentType
from app.services.chunking import Chunk
from app.services.reembed_service import ReembedService


class _StampingContextualizer:
    """Mimics F103.d's stamp behaviour without any LLM calls."""

    model_name = "stamp"

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def contextualize(self, document, chunks):
        self.calls.append((str(document.id), len(chunks)))
        document.metadata_ = {
            **(document.metadata_ or {}),
            "contextualization_version": CONTEXTUALIZATION_VERSION,
        }
        # Pass chunks through with a non-null context so the
        # downstream "contextualized count" is non-zero.
        return [Chunk(text=c.text, metadata=c.metadata, context="ctx") for c in chunks]


class _RecordingEmbedding:
    """Captures index_document + remove_document calls. The real
    EmbeddingService writes to Chroma + Postgres; this records the
    call and mutates the doc's version stamps so the tests can
    assert downstream behaviour."""

    def __init__(self) -> None:
        self.indexed: list[tuple[str, int]] = []
        self.removed: list[str] = []

    def index_document(self, doc, *, chunks=None, elements=None) -> None:
        self.indexed.append((str(doc.id), len(chunks or [])))
        doc.chunking_version = "v3-heading-as-metadata"
        doc.embedding_model_version = "test-embedder"

    def remove_document(self, document_id: str) -> None:
        self.removed.append(document_id)


def _seed_doc_with_elements(
    session: Session, *, owner_id, filename: str = "doc.pdf"
) -> Document:
    doc = Document(
        owner_id=owner_id,
        filename=filename,
        mime_type="application/pdf",
        size_bytes=100,
        storage_key=f"key-{uuid4()}",
        status=DocumentStatus.READY,
        document_type=DocumentType.OTHER,
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
    session.refresh(doc)
    return doc


# ---------- happy path ----------


@pytest.mark.asyncio
async def test_reembed_calls_contextualize_then_index_once(admin_user) -> None:
    with Session(sync_engine) as session:
        doc = _seed_doc_with_elements(session, owner_id=admin_user.id)

        ctx = _StampingContextualizer()
        emb = _RecordingEmbedding()
        service = ReembedService(session=session, embedding=emb, contextualizer=ctx)

        service.reembed_document(doc)

        assert len(ctx.calls) == 1
        assert len(emb.indexed) == 1
        assert emb.indexed[0][0] == str(doc.id)


@pytest.mark.asyncio
async def test_reembed_clears_then_upserts_to_drop_stale_chunks(admin_user) -> None:
    """Plan §4: remove-then-index protects against the rare case
    where the new chunk count is smaller than the old (would leave
    stale chunks in Chroma otherwise)."""
    with Session(sync_engine) as session:
        doc = _seed_doc_with_elements(session, owner_id=admin_user.id)

        ctx = _StampingContextualizer()
        emb = _RecordingEmbedding()
        service = ReembedService(session=session, embedding=emb, contextualizer=ctx)

        service.reembed_document(doc)

        assert emb.removed == [str(doc.id)]
        assert len(emb.indexed) == 1


@pytest.mark.asyncio
async def test_reembed_stamps_contextualization_version(admin_user) -> None:
    with Session(sync_engine) as session:
        doc = _seed_doc_with_elements(session, owner_id=admin_user.id)
        doc_id = doc.id

        ctx = _StampingContextualizer()
        emb = _RecordingEmbedding()
        service = ReembedService(session=session, embedding=emb, contextualizer=ctx)

        service.reembed_document(doc)
        session.commit()

    # Re-fetch from a fresh session to verify the stamp persisted.
    with Session(sync_engine) as session:
        fresh = session.get(Document, doc_id)
        assert fresh.metadata_["contextualization_version"] == CONTEXTUALIZATION_VERSION


# ---------- short-circuit paths ----------


@pytest.mark.asyncio
async def test_reembed_skips_doc_without_elements(admin_user) -> None:
    """A doc whose elements never persisted (failed extraction, or
    re-uploaded with a chunk_version mismatch) should bail out
    cleanly rather than try to index zero chunks."""
    with Session(sync_engine) as session:
        doc = Document(
            owner_id=admin_user.id,
            filename="empty.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            storage_key=f"key-{uuid4()}",
            status=DocumentStatus.READY,
            extracted_text="text but no elements",
            metadata_={},
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        ctx = _StampingContextualizer()
        emb = _RecordingEmbedding()
        service = ReembedService(session=session, embedding=emb, contextualizer=ctx)

        service.reembed_document(doc)

        assert ctx.calls == []
        assert emb.indexed == []


@pytest.mark.asyncio
async def test_reembed_skips_doc_without_text(admin_user) -> None:
    with Session(sync_engine) as session:
        doc = Document(
            owner_id=admin_user.id,
            filename="empty.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            storage_key=f"key-{uuid4()}",
            status=DocumentStatus.READY,
            extracted_text=None,
            metadata_={},
        )
        session.add(doc)
        session.commit()

        ctx = _StampingContextualizer()
        emb = _RecordingEmbedding()
        service = ReembedService(session=session, embedding=emb, contextualizer=ctx)

        service.reembed_document(doc)

        assert ctx.calls == []
        assert emb.indexed == []
