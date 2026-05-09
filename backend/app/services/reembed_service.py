"""F103.c.2 — targeted re-embed for one document.

Worker-side service. Re-runs the chunking + contextualization +
embedding path for a single ``Document`` so a recent metadata
change (notably ``authored_by_id`` being set or cleared by the
F103.c.2 manual-override route) lands in the new vectors without
re-doing the entire corpus.

Symmetric with ``SyncCandidateService`` and
``AuthorLinkageService``: synchronous, takes a sync ``Session``,
never raises into the caller's transaction (failures are logged
and the Celery task layer decides whether to retry).

The same chunk-build pipeline lives in three places now:

- ``ExtractionService._index`` — runs at ingestion.
- ``scripts/reindex_embeddings.py`` — corpus-wide re-embed.
- ``ReembedService.reembed_document`` — single-doc re-embed
  (this module).

All three converge on ``elements_from_orm → chunk_elements →
contextualize → EmbeddingService.index_document``. The script
can call into this service to share the loop body.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.chunking import chunk_elements
from app.services.embedding_service import elements_from_orm

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.adapters.protocols import ChunkContextualizer
    from app.models import Document
    from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class ReembedService:
    """Targeted single-document re-embed."""

    def __init__(
        self,
        session: Session,
        embedding: EmbeddingService,
        contextualizer: ChunkContextualizer,
    ) -> None:
        self._session = session
        self._embedding = embedding
        self._contextualizer = contextualizer

    def reembed_document(self, document: Document) -> None:
        """Re-run the chunk-build pipeline for ``document`` and upsert
        fresh chunk vectors + the doc-level vector. Stamps
        ``contextualization_version`` per the F103.d contract.

        ``EmbeddingService.index_document`` upserts keyed by
        ``(doc_id, chunk_index)``; subsequent calls overwrite the
        prior vectors for unchanged chunks but **leave stale
        chunks behind** if the new chunk count is smaller than the
        old (extremely rare — would require chunking_version to
        change between runs). Mitigation: ``remove_document``
        before ``index_document`` clears the slate. We do that to
        be safe; the cost is one extra Chroma round-trip per
        re-embed, which is well under the LLM cost.
        """
        if not document.elements:
            logger.warning(
                "reembed: document %s has no persisted elements; skipping",
                document.id,
            )
            return
        if not document.extracted_text:
            logger.warning(
                "reembed: document %s has no extracted text; skipping",
                document.id,
            )
            return

        elements = elements_from_orm(document.elements)
        chunks = chunk_elements(elements)
        if not chunks:
            logger.warning(
                "reembed: document %s chunked to zero; skipping", document.id
            )
            return

        # Run the contextualizer; it stamps
        # ``metadata['contextualization_version']`` on the document
        # at the end of a successful pass per the F103.d contract.
        chunks = self._contextualizer.contextualize(document, chunks)

        # Clear-then-upsert pattern. Defends against the rare case
        # where the chunk count shrinks between runs (would leave
        # stale chunk vectors in Chroma otherwise).
        self._embedding.remove_document(str(document.id))
        self._embedding.index_document(document, chunks=chunks)

        logger.info(
            "reembed: document %s re-indexed with %d chunks",
            document.id,
            len(chunks),
        )


__all__ = ["ReembedService"]
