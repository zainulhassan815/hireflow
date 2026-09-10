"""Context-gate diversity: near-duplicate suppression and the
per-document cap.

The gate is a staticmethod over already-ranked chunks, so these
exercise it directly — no retriever, no LLM, no database.
"""

from __future__ import annotations

from uuid import uuid4

from app.adapters.protocols import RetrievedChunk
from app.services.rag_service import RagService

_BUDGET = 10_000
# The shipped ``rag_context_token_budget``; the monopoly case only
# reproduces when the budget can actually be exhausted.
_REAL_BUDGET = 4000


def _chunk(document_id, index: int, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=document_id,
        filename="challan.pdf",
        chunk_index=index,
        text=text,
        distance=0.30,
        score=1.0 - index / 100,
    )


def test_literal_repeats_collapse_to_one() -> None:
    """A form whose sections repeat verbatim contributes one copy.

    Whitespace and case differ between the bank, student and office
    copies of a challan; the paragraph does not.
    """
    doc = uuid4()
    chunks = [
        _chunk(doc, 0, "Admission fee payable is Rs. 45,000 before 30 September."),
        _chunk(doc, 1, "ADMISSION   fee payable is Rs. 45,000 before 30 September."),
        _chunk(doc, 2, "admission fee payable is Rs. 45,000 before 30 September.\n"),
    ]

    kept, _ = RagService._apply_context_gate(chunks, None, _BUDGET, per_document_cap=3)

    assert [c.chunk_index for c in kept] == [0]


def test_one_document_cannot_monopolise_the_context() -> None:
    """The observed failure, at the real token budget.

    A 14-chunk form ranked above everything else exhausts the budget
    before any other document is reached, so the chunk actually
    carrying the answer never reaches the model. The chunks are
    distinct, so dedup does not fire here — the cap does.
    """
    challan, resume = uuid4(), uuid4()
    body = "x" * 2400  # ~600 tokens, a realistic chunk
    chunks = [_chunk(challan, i, f"Challan section {i}. {body}") for i in range(14)]
    chunks.append(_chunk(resume, 0, f"Sara holds a BSc in Computer Science. {body}"))

    kept, _ = RagService._apply_context_gate(
        chunks, None, _REAL_BUDGET, per_document_cap=3
    )

    assert sum(c.document_id == challan for c in kept) == 3
    assert resume in {c.document_id for c in kept}


def test_cap_counts_distinct_content_not_repeats() -> None:
    """Dedup runs first, so the allowance is spent on distinct chunks.

    Capping before dedup would burn all three slots on one repeated
    paragraph and drop the chunk carrying the answer.
    """
    doc = uuid4()
    repeated = "Bank copy: deposit at any branch."
    chunks = [
        _chunk(doc, 0, repeated),
        _chunk(doc, 1, repeated),
        _chunk(doc, 2, repeated),
        _chunk(doc, 3, "Admission fee payable is Rs. 45,000."),
    ]

    kept, _ = RagService._apply_context_gate(chunks, None, _BUDGET, per_document_cap=3)

    assert [c.chunk_index for c in kept] == [0, 3]


def test_pinned_documents_are_exempt_from_the_cap() -> None:
    """ "Summarize this offer letter" legitimately wants the whole file;
    a caller who named the document has already expressed intent."""
    doc = uuid4()
    chunks = [_chunk(doc, i, f"Clause {i} of the offer.") for i in range(6)]

    kept, _ = RagService._apply_context_gate(
        chunks, None, _BUDGET, per_document_cap=None
    )

    assert len(kept) == 6


def test_dedup_still_applies_to_pinned_documents() -> None:
    """Exempting the cap must not re-admit literal repeats."""
    doc = uuid4()
    chunks = [_chunk(doc, i, "The same clause, thrice.") for i in range(3)]

    kept, _ = RagService._apply_context_gate(
        chunks, None, _BUDGET, per_document_cap=None
    )

    assert len(kept) == 1


def test_shared_boilerplate_does_not_collapse_across_documents() -> None:
    """Dedup is per document, not global.

    Three offer letters cut from one template share their opening
    paragraph. Collapsing those into a single citation would drop two
    real documents from the answer — the failure this gate exists to
    prevent, arriving by the opposite route.
    """
    letters = [uuid4() for _ in range(3)]
    boilerplate = "We are pleased to offer you the position described below."
    chunks = [_chunk(doc, 0, boilerplate) for doc in letters]

    kept, _ = RagService._apply_context_gate(chunks, None, _BUDGET, per_document_cap=3)

    assert {c.document_id for c in kept} == set(letters)
