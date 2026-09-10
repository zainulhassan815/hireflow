"""Starvation guard for RAG's chunk lane.

A question that retrieves zero chunks gets the no-hits sentinel instead
of an answer, and `p@5` cannot see that: it measures ``search()``,
which returns *documents* and is rescued by its lexical lane. RAG has
no such rescue — lexical hits only boost vector-retrieved chunks, they
never introduce one — so the vector ceiling alone decides whether a
question is answerable at all.

Measured on the fixture corpus, positive questions retrieving nothing:

    ceiling   starved   chunks leaked to 'quantum chromodynamics'
    0.35        7/21      0
    0.40        5/21      0
    0.45        2/21      1     <- shipped
    0.50        1/21      4
    0.55        0/21      7

0.45 is the knee. The two that still starve ("anyone", "k8s") carry
almost no vector signal and are answered by the lexical lane in
``search()``.
"""

from __future__ import annotations

import pytest

from tests.eval.dataset import EVAL_QUERIES

# Ceiling above which the corpus is mostly noise. Raising this rescues
# few questions and leaks many chunks — see the table above.
_MAX_STARVED = 2


async def _chunk_counts(eval_owner) -> dict[str, int]:
    from app.adapters.chroma_store import ChromaVectorStore
    from app.adapters.embeddings.registry import get_embedding_provider
    from app.adapters.rerankers.registry import get_reranker
    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.repositories.document import DocumentRepository
    from app.services.search_service import SearchService

    store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        embedder=get_embedding_provider(settings),
    )
    counts: dict[str, int] = {}
    async with SessionLocal() as session:
        service = SearchService(
            DocumentRepository(session), store, reranker=get_reranker(settings)
        )
        for case in EVAL_QUERIES:
            chunks = await service.retrieve_chunks(
                actor=eval_owner, query=case.query, document_ids=None, limit=10
            )
            counts[case.query] = len(chunks)
    return counts


@pytest.mark.usefixtures("slug_to_document_id")
async def test_few_questions_starve_at_the_shipped_ceiling(eval_owner) -> None:
    counts = await _chunk_counts(eval_owner)
    starved = [
        case.query
        for case in EVAL_QUERIES
        if case.bucket != "negative" and case.expected_docs and not counts[case.query]
    ]
    print(f"\nstarved: {len(starved)} -> {starved}")
    assert len(starved) <= _MAX_STARVED, (
        f"{len(starved)} positive questions retrieve zero chunks and cannot be "
        f"answered at all: {starved}"
    )


@pytest.mark.usefixtures("slug_to_document_id")
async def test_the_looser_ceiling_still_starves_clear_nonsense(eval_owner) -> None:
    """The looser ceiling trades a little precision for answerability.

    'sourdough bread' must still retrieve nothing; 'quantum
    chromodynamics' is allowed a token amount, which the reranker and
    the context gate then have to deal with.
    """
    counts = await _chunk_counts(eval_owner)
    assert counts["recipe for sourdough bread"] == 0
    assert counts["quantum chromodynamics tensor networks"] <= 2
