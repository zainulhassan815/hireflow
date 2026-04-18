"""Acronym expansion for search queries (F88.b).

Catch the common asymmetry where users type abbreviations and documents
use the canonical form. One-directional only: ``K8s`` becomes
``kubernetes`` in the query string before it reaches FTS. Documents
that contain only the abbreviation are not matched here — that needs
a real Postgres synonym dictionary, which is filesystem-installed
on the server. Captured as a follow-up.

Applied only to the lexical (FTS) path. The vector path already
understands ``K8s ≈ Kubernetes`` semantically — feeding it the
canonical form would add noise without changing recall.
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
