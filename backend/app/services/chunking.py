"""Text chunking for vector embedding.

Splits text into overlapping chunks suitable for semantic search. Uses a
simple recursive character splitter — good enough for most document types
and easy to reason about.
"""

from __future__ import annotations

_DEFAULT_CHUNK_SIZE = 500
_DEFAULT_OVERLAP = 100
_SEPARATORS = ["\n\n", "\n", ". ", " "]


def chunk_text(
    text: str,
    *,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    overlap: int = _DEFAULT_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks.

    Tries to split on paragraph boundaries first, then sentences, then
    words. Each chunk overlaps with the previous by ``overlap`` characters
    to preserve context across boundaries.
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    if len(text) <= chunk_size:
        return [text]

    chunks = _recursive_split(text, chunk_size, _SEPARATORS)
    return _apply_overlap(chunks, overlap)


def _recursive_split(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    if not separators:
        # Fallback: hard split by character count
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    sep = separators[0]
    parts = text.split(sep)
    chunks: list[str] = []
    current = ""

    for part in parts:
        candidate = f"{current}{sep}{part}" if current else part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(part) > chunk_size:
                chunks.extend(_recursive_split(part, chunk_size, separators[1:]))
            else:
                current = part
                continue
            current = ""

    if current:
        chunks.append(current)

    return chunks


def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev_tail = chunks[i - 1][-overlap:]
        result.append(prev_tail + chunks[i])

    return result
