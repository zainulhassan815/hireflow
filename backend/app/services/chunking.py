"""Element-aware chunking (F82.e).

Consumes the typed ``Element`` list from ``UnstructuredExtractor`` and
emits ``Chunk`` objects with text + metadata (``chunk_kind``,
``section_heading``, ``page_number``, ``element_kinds``). Downstream
(Chroma) uses this metadata for filtering, display, and future
section-aware retrieval.

Rules walking elements in reading order:

1. A ``Title`` / heading element starts a new chunk and becomes the
   ``section_heading`` for every subsequent non-heading chunk until the
   next heading.
2. A ``Table`` element is its own chunk (``chunk_kind="table"``). If
   unstructured produced an HTML table, we keep the HTML as metadata
   for downstream display.
3. A run of ``ListItem`` elements is kept together in one chunk as
   long as the accumulated size stays ≤ target.
4. ``NarrativeText`` (and anything unrecognised) is packed greedily
   with surrounding narrative up to target size.
5. Tiny doc short-circuit — ≤3 elements total or ≤1500 chars of text
   → a single chunk per heading region.
6. An oversize single paragraph falls back to a sentence splitter for
   that element only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.adapters.protocols import Element

# Reading order targets for chunking. Numbers tuned for bge-small's
# 512-token input limit (≈2000 English chars) with headroom for the
# section-heading prefix we add during contextual retrieval (F82.c).
_TARGET_CHARS = 1200
_MAX_CHARS_SOFT = 1500  # packing stops adding elements past this
_TINY_DOC_THRESHOLD = 1500

# Element kinds that end/start a chunk regardless of size.
_HEADING_KINDS = frozenset({"Title", "Header"})
_TABLE_KINDS = frozenset({"Table"})
_LIST_KINDS = frozenset({"ListItem"})


# Bump when the chunking rules change in a way that invalidates existing
# vectors. Consumed by documents.chunking_version.
CHUNKING_VERSION = "v2-element-aware"


@dataclass(frozen=True)
class Chunk:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    # F82.c: populated by ``ChunkContextualizer.contextualize``.
    # Prepended to ``text`` at embed time (but not at display time).
    context: str | None = None


def chunk_elements(elements: list[Element]) -> list[Chunk]:
    """Turn a list of typed elements into retrieval-ready chunks.

    Pure function — no I/O, no shared state. Deterministic for a given
    input.
    """
    if not elements:
        return []

    # Tiny-doc short-circuit: dump the whole thing into one chunk and
    # keep the first heading (if any) as the section_heading.
    total_text = sum(len(e.text) for e in elements)
    if total_text <= _TINY_DOC_THRESHOLD:
        return [_single_chunk(elements)]

    chunks: list[Chunk] = []
    current_heading: str | None = None
    narrative_buffer: list[Element] = []

    def flush_narrative() -> None:
        if not narrative_buffer:
            return
        chunks.extend(_pack_narrative(narrative_buffer, current_heading))
        narrative_buffer.clear()

    for element in elements:
        if element.kind in _HEADING_KINDS:
            flush_narrative()
            current_heading = element.text
            chunks.append(
                Chunk(
                    text=element.text,
                    metadata={
                        "chunk_kind": "heading",
                        "section_heading": element.text,
                        "element_kinds": [element.kind],
                        "page_number": element.page_number,
                    },
                )
            )
            continue

        if element.kind in _TABLE_KINDS:
            flush_narrative()
            chunks.append(_table_chunk(element, current_heading))
            continue

        # Narrative + list items accumulate together. Keeping lists mixed
        # with surrounding narrative is actually what you want for
        # "bulleted skills under SKILLS heading"-type layouts.
        narrative_buffer.append(element)

    flush_narrative()
    return chunks


def _single_chunk(elements: list[Element]) -> Chunk:
    """All-in-one chunk for tiny docs. Picks the first heading if any."""
    heading = next(
        (e.text for e in elements if e.kind in _HEADING_KINDS),
        None,
    )
    pages = {e.page_number for e in elements if e.page_number is not None}
    return Chunk(
        text="\n\n".join(e.text for e in elements),
        metadata={
            "chunk_kind": "document",
            "section_heading": heading,
            "element_kinds": sorted({e.kind for e in elements}),
            "page_number": min(pages) if pages else None,
        },
    )


def _table_chunk(element: Element, heading: str | None) -> Chunk:
    """Tables become their own chunks. Keep HTML if unstructured gave it,
    otherwise the plain flattened text."""
    text = element.metadata.get("text_as_html") or element.text
    return Chunk(
        text=text,
        metadata={
            "chunk_kind": "table",
            "section_heading": heading,
            "element_kinds": ["Table"],
            "page_number": element.page_number,
        },
    )


def _pack_narrative(elements: list[Element], heading: str | None) -> list[Chunk]:
    """Greedily pack narrative/list elements to the target size.

    Emits a new chunk when the next element would push us past the soft
    max. An element that alone exceeds the target is split on sentence
    boundaries.
    """
    chunks: list[Chunk] = []
    buf_texts: list[str] = []
    buf_kinds: set[str] = set()
    buf_pages: set[int] = set()
    buf_len = 0

    def emit() -> None:
        nonlocal buf_texts, buf_kinds, buf_pages, buf_len
        if not buf_texts:
            return
        chunks.append(
            Chunk(
                text="\n\n".join(buf_texts),
                metadata={
                    "chunk_kind": "narrative",
                    "section_heading": heading,
                    "element_kinds": sorted(buf_kinds),
                    "page_number": min(buf_pages) if buf_pages else None,
                },
            )
        )
        buf_texts = []
        buf_kinds = set()
        buf_pages = set()
        buf_len = 0

    for element in elements:
        text = element.text
        # Oversize single element — split on sentences.
        if len(text) > _MAX_CHARS_SOFT:
            emit()
            for piece in _split_oversized(text, _TARGET_CHARS):
                chunks.append(
                    Chunk(
                        text=piece,
                        metadata={
                            "chunk_kind": "narrative",
                            "section_heading": heading,
                            "element_kinds": [element.kind],
                            "page_number": element.page_number,
                        },
                    )
                )
            continue

        # If appending would push us past the soft max, flush first.
        if buf_len > 0 and buf_len + len(text) + 2 > _MAX_CHARS_SOFT:
            emit()

        buf_texts.append(text)
        buf_kinds.add(element.kind)
        if element.page_number is not None:
            buf_pages.add(element.page_number)
        buf_len += len(text) + 2  # +2 for the "\n\n" joiner

        # If we've already hit the target, emit now rather than
        # accumulate to the soft max. Keeps chunks close to target size.
        if buf_len >= _TARGET_CHARS:
            emit()

    emit()
    return chunks


def _split_oversized(text: str, target: int) -> list[str]:
    """Split a too-large paragraph on sentence boundaries, then whitespace.

    Last-resort hard char-cut if a single sentence is enormous. Rare in
    practice — run-on legal clauses, boilerplate.
    """
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    pieces: list[str] = []
    current = ""
    for sent in sentences:
        if not sent:
            continue
        candidate = f"{current} {sent}".strip() if current else sent
        if len(candidate) <= target:
            current = candidate
        else:
            if current:
                pieces.append(current)
            if len(sent) > target:
                for i in range(0, len(sent), target):
                    pieces.append(sent[i : i + target])
                current = ""
            else:
                current = sent
    if current:
        pieces.append(current)
    return pieces
