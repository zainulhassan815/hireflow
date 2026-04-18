"""Query-side normalization for search (F88.b + F88.d).

Two pure helpers, both applied only to the lexical (FTS) path. The
vector path already handles equivalence semantically — feeding it
normalized text adds noise without changing recall.

* ``expand_acronyms`` (F88.b) catches the asymmetry where users type
  abbreviations and documents use the canonical form. One-directional:
  ``K8s`` becomes ``kubernetes``.
* ``normalize_tech_tokens`` (F88.d) preserves tech tokens
  (``C++``, ``.NET``, ``Node.js`` …) that the english analyzer
  would otherwise strip. The exact same substitution runs at index
  time inside the ``search_tsv`` generated column via the SQL
  ``normalize_tech_tokens(text)`` function — both sides MUST stay in
  sync or queries silently miss matches.
"""

from __future__ import annotations

import re

# Conservative table. Ambiguous abbreviations (``cv``: curriculum vitae
# vs computer vision; ``tf``: terraform vs tensorflow) are intentionally
# omitted — expansion would hurt more than it helps. Add only when the
# corpus / queries justify it.
_ACRONYMS: dict[str, str] = {
    "js": "javascript",
    "ts": "typescript",
    "k8s": "kubernetes",
    "k8": "kubernetes",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "ui": "user interface",
    "ux": "user experience",
    "qa": "quality assurance",
    "sre": "site reliability engineering",
    "sde": "software development engineer",
    "swe": "software engineer",
    "pm": "project manager",
    "po": "product owner",
    "ba": "business analyst",
    "ds": "data scientist",
    "de": "data engineer",
    "mle": "machine learning engineer",
    "nlp": "natural language processing",
    "db": "database",
    "gcp": "google cloud platform",
    "aws": "amazon web services",
    "fe": "frontend",
    "be": "backend",
}

# Tokens that we'll consider for expansion. Same vocabulary as
# F92.1's highlight tokenizer roughly: alphanumerics plus a few
# tech token chars. Quoted phrases pass through untouched so
# F88.a's websearch syntax keeps working.
_TOKEN_RE = re.compile(r"\".*?\"|[A-Za-z][A-Za-z0-9+#.\-]*")


def expand_acronyms(query: str) -> str:
    """Return ``query`` with known abbreviations replaced by canonical forms.

    Case-insensitive on lookup; canonical form is always lowercase, but
    Postgres FTS lowercases anyway so it doesn't matter for the index
    side. Quoted substrings (``"machine learning"`` etc.) are left
    untouched so phrase semantics are preserved.

    Pure function — no side effects, safe to call from anywhere.
    """
    if not query:
        return query

    def _swap(match: re.Match[str]) -> str:
        token = match.group(0)
        # Phrase / quoted strings: leave alone.
        if token.startswith('"'):
            return token
        canonical = _ACRONYMS.get(token.lower())
        return canonical if canonical is not None else token

    return _TOKEN_RE.sub(_swap, query)


# F88.d: tech-token substitutions. ORDER MATTERS — Node.js must run
# before any C-prefixed match. The SQL function
# ``normalize_tech_tokens(text)`` (see migration 2347719a1bd8) runs the
# exact same substitutions on the index side; keep these in sync.
_TECH_TOKEN_SUBSTITUTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"Objective-C", re.IGNORECASE), "objectivec"),
    (re.compile(r"Node\.js", re.IGNORECASE), "nodejs"),
    (re.compile(r"\bC\+\+", re.IGNORECASE), "cpp"),
    (re.compile(r"\bC#", re.IGNORECASE), "csharp"),
    (re.compile(r"\bF#", re.IGNORECASE), "fsharp"),
    # `\b` for `.NET` would require a word char before `.`; use a
    # non-look-behind alternative: match `.NET` not preceded by a letter
    # by anchoring to a non-letter position. Python doesn't need the
    # Postgres-specific anchors used in the SQL function.
    (re.compile(r"(?<![A-Za-z])\.NET\b", re.IGNORECASE), "dotnet"),
]


def normalize_tech_tokens(text: str) -> str:
    """Substitute special tech tokens with safe alphabetic equivalents.

    Mirror of the Postgres ``normalize_tech_tokens(text)`` SQL function
    used inside the ``search_tsv`` generated column. Both sides must
    stay in sync; if you add an entry here, add it to the migration
    too (and write a test in ``test_document_fts.py`` that proves
    a doc indexed via the SQL function matches a query normalized
    via this Python function).
    """
    if not text:
        return text
    for pattern, replacement in _TECH_TOKEN_SUBSTITUTIONS:
        text = pattern.sub(replacement, text)
    return text
