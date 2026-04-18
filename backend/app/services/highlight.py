"""Query-term match-span extraction for snippet highlighting.

The API returns plain snippet text plus ``match_spans`` — a list of
``(start, end)`` byte offsets — instead of injecting ``<mark>`` tags.
That keeps responses presentation-neutral and removes the XSS surface
on the frontend.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Conservative English stopword list. Anything in here would just
# add visual noise if highlighted (every result has "the").
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "or",
        "the",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "with",
        "by",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "i",
        "me",
        "my",
        "we",
        "you",
        "your",
        "they",
        "them",
        "this",
        "that",
        "these",
        "those",
        "what",
        "who",
        "when",
        "where",
        "why",
        "how",
        "which",
        "all",
        "any",
        "some",
        "no",
        "not",
        "as",
        "if",
        "but",
        "from",
        "up",
        "out",
        "about",
    }
)

# Capture identifiers including tech tokens like c++, c#, .net, node.js.
# An optional leading dot allows ".net" to survive as a single token
# (the regex's main body still requires a letter before any further punctuation).
_TOKEN_RE = re.compile(r"\.?[A-Za-z][A-Za-z0-9+#.\-]*")


def extract_query_terms(query: str) -> list[str]:
    """Tokenize a query into highlight-worthy terms (lowercased, deduped)."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _TOKEN_RE.finditer(query.lower()):
        token = match.group(0).rstrip(".-")  # trim trailing punctuation
        if len(token) <= 1 or token in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def find_match_spans(text: str, terms: Iterable[str]) -> list[tuple[int, int]]:
    """Return non-overlapping ``[start, end)`` offsets of term matches in ``text``.

    Word boundaries are used for purely alphanumeric terms (so ``java``
    doesn't match inside ``javascript``). Terms with non-word characters
    (``c++``, ``.net``) fall back to plain substring match because the
    regex ``\\b`` boundary requires a word/non-word transition that
    doesn't apply to tokens already starting or ending in non-word chars.
    """
    term_list = [t for t in terms if t]
    if not term_list or not text:
        return []

    parts: list[str] = []
    for term in term_list:
        escaped = re.escape(term)
        parts.append(rf"\b{escaped}\b" if term.isalnum() else escaped)

    rx = re.compile("|".join(parts), re.IGNORECASE)
    spans = [(m.start(), m.end()) for m in rx.finditer(text)]
    return _merge_overlaps(spans)


def _merge_overlaps(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return spans
    spans.sort()
    merged: list[tuple[int, int]] = [spans[0]]
    for start, end in spans[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged
