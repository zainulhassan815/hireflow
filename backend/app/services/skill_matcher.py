"""Shared skill-vocabulary matcher.

Single source of truth for "does this text contain known skill X?". Used
by both:

- ``HeuristicQueryParser`` (F89.a) on user queries — was the original
  home for ``_skill_match``.
- ``RuleBasedClassifier`` (F103.b) on extracted document text — used to
  carry its own narrower regex; consolidated here.

The matcher uses a non-alphanumeric boundary check (not regex ``\\b``) so
skills with special characters (``c++``, ``.net``, ``node.js``) match
correctly. ``\\b`` treats the ``+`` in ``c++`` as a boundary itself,
which silently drops every special-char skill from any sweep.
"""

from __future__ import annotations

from app.services.query_parser_vocab import KNOWN_SKILLS

# Pre-sorted longest-first so multi-word skills (``machine learning``)
# claim character ranges before single-word skills inside them
# (``learning``) get a chance.
_SKILLS_LONGEST_FIRST: tuple[str, ...] = tuple(
    sorted(KNOWN_SKILLS, key=len, reverse=True)
)


def find_skill(text_lower: str, skill_lower: str) -> tuple[int, int] | None:
    """Locate ``skill_lower`` inside ``text_lower`` with non-alphanumeric
    boundary on both sides. Returns the ``(start, end)`` span of the
    first match, or ``None``. Both inputs must already be lowercase.
    """
    idx = 0
    while True:
        pos = text_lower.find(skill_lower, idx)
        if pos == -1:
            return None
        left_ok = pos == 0 or not text_lower[pos - 1].isalnum()
        end = pos + len(skill_lower)
        right_ok = end == len(text_lower) or not text_lower[end].isalnum()
        if left_ok and right_ok:
            return (pos, end)
        idx = pos + 1


def extract_skills(text: str) -> list[str]:
    """Return every ``KNOWN_SKILLS`` token present in ``text``, sorted.

    Longest-first iteration with claimed-range tracking ensures
    ``machine learning`` is recorded before ``learning`` can match the
    same span. Output is deduped (per-skill presence, not mention count)
    and sorted alphabetically for stable downstream consumers.
    """
    text_lower = text.lower()
    claimed: list[tuple[int, int]] = []
    hits: set[str] = set()
    for skill in _SKILLS_LONGEST_FIRST:
        match = find_skill(text_lower, skill)
        if match is None:
            continue
        if any(not (match[1] <= start or match[0] >= end) for start, end in claimed):
            continue
        claimed.append(match)
        hits.add(skill)
    return sorted(hits)


__all__ = ["extract_skills", "find_skill"]
