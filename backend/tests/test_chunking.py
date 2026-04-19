"""F82.e: element-aware chunker unit tests.

Pure function under test (``chunk_elements``). No DB, no I/O.
"""

from __future__ import annotations

from app.adapters.protocols import Element
from app.services.chunking import Chunk, chunk_elements


def _narr(text: str, order: int, page: int = 1) -> Element:
    return Element(kind="NarrativeText", text=text, page_number=page, order=order)


def _title(text: str, order: int, page: int = 1) -> Element:
    return Element(kind="Title", text=text, page_number=page, order=order)


def _list_item(text: str, order: int, page: int = 1) -> Element:
    return Element(kind="ListItem", text=text, page_number=page, order=order)


def _table(text: str, order: int, page: int = 1, html: str | None = None) -> Element:
    meta = {"text_as_html": html} if html else {}
    return Element(
        kind="Table", text=text, page_number=page, order=order, metadata=meta
    )


# ---------- edge cases ----------


def test_empty_input_returns_empty() -> None:
    assert chunk_elements([]) == []


def test_tiny_doc_collapses_to_single_chunk() -> None:
    """Short doc → one chunk regardless of element count."""
    elements = [
        _title("CONTACT", 0),
        _narr("Email: a@b.com", 1),
    ]
    chunks = chunk_elements(elements)
    assert len(chunks) == 1
    assert "CONTACT" in chunks[0].text
    assert chunks[0].metadata["chunk_kind"] == "document"
    assert chunks[0].metadata["section_heading"] == "CONTACT"


# ---------- heading handling ----------


def test_title_attaches_as_metadata_not_its_own_chunk() -> None:
    """Headings are NOT emitted as standalone chunks.

    A heading-only chunk (e.g. just the word 'SKILLS') is poor retrieval
    signal; its useful role is as metadata on the content that follows.
    The chunker tracks the current heading and attaches it as
    ``section_heading`` on subsequent narrative chunks.
    """
    narr_body = "x " * 800  # force past tiny-doc threshold
    elements = [
        _narr(narr_body, 0),
        _title("SKILLS", 1),
        _narr("Python, Django, AWS", 2),
    ]
    chunks = chunk_elements(elements)

    # No chunk should be kind="heading" — we don't emit those anymore.
    assert not any(c.metadata.get("chunk_kind") == "heading" for c in chunks)

    # The narrative chunk under SKILLS should carry section_heading.
    skills_narrs = [
        c
        for c in chunks
        if c.metadata.get("chunk_kind") == "narrative"
        and c.metadata.get("section_heading") == "SKILLS"
    ]
    assert skills_narrs, "Expected narrative chunk under SKILLS heading"
    assert "Python" in skills_narrs[0].text


def test_multiple_headings_track_current_section() -> None:
    """Each new heading replaces the current section on subsequent chunks."""
    # Must exceed tiny-doc threshold (1500) so the chunker actually
    # walks elements instead of collapsing into a single chunk.
    big = "x " * 1000
    elements = [
        _narr(big, 0),
        _title("EXPERIENCE", 1),
        _narr("Engineer at ACME, 2020-2024", 2),
        _title("SKILLS", 3),
        _narr("Python, SQL, Docker", 4),
    ]
    chunks = chunk_elements(elements)

    # At least one narrative under EXPERIENCE and one under SKILLS.
    experience = [
        c
        for c in chunks
        if c.metadata.get("section_heading") == "EXPERIENCE" and "ACME" in c.text
    ]
    skills = [
        c
        for c in chunks
        if c.metadata.get("section_heading") == "SKILLS" and "Python" in c.text
    ]
    assert experience, "Expected a narrative chunk tagged with EXPERIENCE heading"
    assert skills, "Expected a narrative chunk tagged with SKILLS heading"


# ---------- tables ----------


def test_table_becomes_its_own_chunk_with_html_preferred() -> None:
    big_narr = "word " * 400  # push past tiny-doc
    table_html = "<table><tr><td>A</td></tr></table>"
    elements = [
        _narr(big_narr, 0),
        _table("A", 1, html=table_html),
    ]
    chunks = chunk_elements(elements)
    tables = [c for c in chunks if c.metadata.get("chunk_kind") == "table"]
    assert len(tables) == 1
    assert tables[0].text == table_html


def test_table_text_fallback_when_no_html() -> None:
    big_narr = "word " * 400
    elements = [
        _narr(big_narr, 0),
        _table("cellA | cellB", 1, html=None),
    ]
    chunks = chunk_elements(elements)
    tables = [c for c in chunks if c.metadata.get("chunk_kind") == "table"]
    assert len(tables) == 1
    assert tables[0].text == "cellA | cellB"


# ---------- narrative packing ----------


def test_narrative_packs_up_to_target_size() -> None:
    """Small paragraphs accumulate into a single chunk until target."""
    # Each paragraph is ~200 chars; 3 should fit, 4th starts a new chunk.
    elements = [_narr("x" * 200, i) for i in range(10)]
    chunks = chunk_elements(elements)
    # All emitted; multiple chunks.
    assert len(chunks) >= 2
    # Every chunk text has length within soft max.
    for c in chunks:
        assert len(c.text) <= 2000  # generous upper bound


def test_narrative_preserves_element_kinds_metadata() -> None:
    big_narr_1 = "word " * 300
    big_narr_2 = "word " * 300
    elements = [
        _narr(big_narr_1, 0),
        _list_item("- item 1", 1),
        _narr(big_narr_2, 2),
    ]
    chunks = chunk_elements(elements)
    # At least one narrative chunk groups the NarrativeText and ListItem.
    mixed = [
        c
        for c in chunks
        if c.metadata.get("chunk_kind") == "narrative"
        and "ListItem" in c.metadata.get("element_kinds", [])
    ]
    assert mixed, "Expected list items to be packed into narrative chunks"


def test_oversized_single_element_falls_back_to_sentence_split() -> None:
    """A paragraph that alone exceeds the soft max is split on sentences."""
    # 2000-char paragraph of distinct sentences.
    big = ". ".join(f"Sentence number {i} with padding" for i in range(1, 120))
    elements = [_narr(big, 0)]
    chunks = chunk_elements(elements)
    assert len(chunks) >= 2
    # None should be silly huge.
    for c in chunks:
        assert len(c.text) <= 2500


# ---------- output shape ----------


def test_chunk_dataclass_shape() -> None:
    chunks = chunk_elements([_narr("hello world", 0)])
    assert len(chunks) == 1
    c = chunks[0]
    assert isinstance(c, Chunk)
    assert c.text == "hello world"
    assert "chunk_kind" in c.metadata
