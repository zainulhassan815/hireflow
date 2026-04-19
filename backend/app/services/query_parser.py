"""F89.a — heuristic natural-language query parser.

Extracts structured filters (years of experience, skills, document
type, date ranges) from user queries so the filters we built in F32
populate automatically from chat. Zero LLM calls — regex + known-
vocabulary lookup, sub-millisecond per query.

Design is conservative by default:
- Extract only high-confidence matches.
- Explicit wins over implicit (an explicit "3 years" overrides the
  "senior" → 5-year threshold).
- Matched spans are preserved so operators can see which tokens the
  parser claimed, and a bad parse is one grep away.
- When nothing matches, ``ParsedFilters.is_empty`` is True and callers
  preserve their pre-F89.a behavior (no SQL path in
  ``SearchService.retrieve_chunks``).

If heuristic accuracy plateaus on the eval harness (currently
targeting >=0.85 F1), the ``QueryParser`` Protocol leaves room for
an LLM-backed parser as a drop-in replacement — that's F89.e, not
this slice.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from app.adapters.protocols import ParsedFilters, QueryIntent

# ---------------------------------------------------------------------------
# Skill matching with a non-alphanumeric boundary check
# ---------------------------------------------------------------------------
# ``\b`` regex word boundaries don't work for skills with special
# characters (``c++``, ``.net``, ``node.js``). We need a custom check:
# the match must be preceded and followed by either a non-alphanumeric
# character or the string boundary. That handles all skills uniformly
# and correctly — "c++" inside "abc++def" doesn't match, but "c++"
# alone or surrounded by spaces/punctuation does.


def _skill_match(text_lower: str, skill_lower: str) -> tuple[int, int] | None:
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


def _keyword_match(text_lower: str, keyword_lower: str) -> tuple[int, int] | None:
    """Same boundary rule as ``_skill_match``; separate for clarity
    since keyword matching has the same semantics but a different
    caller."""
    return _skill_match(text_lower, keyword_lower)


class HeuristicQueryParser:
    """Regex + known-vocabulary parser. See module docstring."""

    # Year-extraction patterns, ordered by specificity. First match
    # wins — once a span is claimed by an earlier (more specific)
    # pattern, later (broader) patterns are not retried on the same
    # span.
    #
    # All numeric captures bounded to two digits ("\d{1,2}") to avoid
    # catastrophic backtracking on pasted paragraphs and to reject
    # years-of-experience claims like "50 years" that are almost
    # certainly not what the user meant.
    _YEAR_PATTERNS: tuple[re.Pattern[str], ...] = (
        # Explicit qualifier patterns first — highest precision.
        re.compile(r"at\s+least\s+(\d{1,2})\s*(?:years?|yrs?)", re.I),
        re.compile(r"over\s+(\d{1,2})\s*(?:years?|yrs?)", re.I),
        re.compile(r"more\s+than\s+(\d{1,2})\s*(?:years?|yrs?)", re.I),
        re.compile(r"(\d{1,2})\+\s*(?:years?|yrs?)", re.I),
        re.compile(r"(\d{1,2})-(\d{1,2})\s*(?:years?|yrs?)", re.I),
        re.compile(r"(\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)?experience", re.I),
        # Loose fallback — "N years" appearing anywhere. Catches
        # "10 years Python" without the word "experience". Last so
        # specific patterns win.
        #
        # Negative lookbehind ``(?<!last\s)`` excludes "last N years"
        # phrases — those are date filters, handled by ``_extract_dates``.
        # Negative lookahead ``(?!\s+ago)`` excludes "N years ago"
        # which talks about elapsed time, not candidate experience.
        re.compile(r"(?<!last\s)(\d{1,2})\s*(?:years?|yrs?)(?!\s+ago)", re.I),
    )

    _RELATIVE_DATE = re.compile(
        r"last\s+(\d{1,3})\s+(day|days|week|weeks|month|months|year|years)",
        re.I,
    )
    # Singular-without-number: "last year", "last month", "last week".
    # Treated as a count of 1.
    _RELATIVE_DATE_SINGULAR = re.compile(
        r"last\s+(day|week|month|year)\b",
        re.I,
    )
    _DATE_SINCE_YEAR = re.compile(r"since\s+(\d{4})", re.I)
    _DATE_AFTER_ISO = re.compile(r"after\s+(\d{4}-\d{2}-\d{2})", re.I)

    def __init__(
        self,
        *,
        seniority: dict[str, int],
        skills: frozenset[str],
        document_types: dict[str, str],
    ) -> None:
        # Lower-case copies for matching; sort longer-first so
        # "mid-level" beats "mid" and "machine learning" beats
        # "learning" alone.
        self._seniority = {k.lower(): v for k, v in seniority.items()}
        self._seniority_keys = sorted(self._seniority.keys(), key=len, reverse=True)
        self._skills_lower = {s.lower() for s in skills}
        self._skills_sorted = sorted(self._skills_lower, key=len, reverse=True)
        self._doctypes = {k.lower(): v for k, v in document_types.items()}
        self._doctype_keys = sorted(self._doctypes.keys(), key=len, reverse=True)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def parse(self, query: str) -> QueryIntent:
        if not query.strip():
            return QueryIntent(
                raw_query=query, filters=ParsedFilters(), matched_spans=()
            )

        spans: list[tuple[int, int, str]] = []

        years = self._extract_years(query, spans)
        # Seniority fires only when no explicit year count matched
        # — explicit beats implicit.
        if years is None:
            years = self._extract_seniority(query, spans)

        skills = self._extract_skills(query, spans)
        doc_type = self._extract_document_type(query, spans)
        date_from, date_to = self._extract_dates(query, spans)

        return QueryIntent(
            raw_query=query,
            filters=ParsedFilters(
                skills=tuple(skills),
                min_experience_years=years,
                document_type=doc_type,
                date_from=date_from,
                date_to=date_to,
            ),
            matched_spans=tuple(spans),
        )

    # ------------------------------------------------------------------
    # Extractors
    # ------------------------------------------------------------------

    def _extract_years(
        self, query: str, spans: list[tuple[int, int, str]]
    ) -> int | None:
        for pattern in self._YEAR_PATTERNS:
            if m := pattern.search(query):
                value = int(m.group(1))
                spans.append((m.start(), m.end(), f"years={value}"))
                return value
        return None

    def _extract_seniority(
        self, query: str, spans: list[tuple[int, int, str]]
    ) -> int | None:
        q = query.lower()
        for token in self._seniority_keys:
            if m := _keyword_match(q, token):
                value = self._seniority[token]
                spans.append((m[0], m[1], f"seniority={token}→{value}"))
                return value
        return None

    def _extract_skills(
        self, query: str, spans: list[tuple[int, int, str]]
    ) -> list[str]:
        q = query.lower()
        hits: list[str] = []
        # Track claimed character ranges so "machine learning" is
        # claimed first and "learning" doesn't re-match the same
        # span. Longest-first iteration (constructor-sorted) ensures
        # the longer skill wins.
        claimed: list[tuple[int, int]] = []
        for skill in self._skills_sorted:
            m = _skill_match(q, skill)
            if m is None:
                continue
            if any(not (m[1] <= s or m[0] >= e) for s, e in claimed):
                # Overlap with a previously-claimed longer skill — skip.
                continue
            claimed.append(m)
            hits.append(skill)
            spans.append((m[0], m[1], f"skill={skill}"))
        return hits

    def _extract_document_type(
        self, query: str, spans: list[tuple[int, int, str]]
    ) -> str | None:
        q = query.lower()
        for keyword in self._doctype_keys:
            if m := _keyword_match(q, keyword):
                value = self._doctypes[keyword]
                spans.append((m[0], m[1], f"doctype={value}"))
                return value
        return None

    def _extract_dates(
        self, query: str, spans: list[tuple[int, int, str]]
    ) -> tuple[datetime | None, datetime | None]:
        """Extract a lower-bound date. Upper-bound ("before X") is
        out of scope in v1; all current HR queries are "since X"
        shaped. Returns ``(date_from, date_to)`` — ``date_to`` is
        always None today.
        """
        now = datetime.now(UTC)

        # Match "last N <unit>" or "last <unit>" (singular = 1).
        m = self._RELATIVE_DATE.search(query)
        amount: int | None = None
        unit: str | None = None
        if m:
            amount = int(m.group(1))
            unit = m.group(2).lower()
            span_tuple = (m.start(), m.end())
        elif s := self._RELATIVE_DATE_SINGULAR.search(query):
            amount = 1
            unit = s.group(1).lower()
            span_tuple = (s.start(), s.end())

        if amount is not None and unit is not None:
            delta: timedelta
            if unit.startswith("day"):
                delta = timedelta(days=amount)
            elif unit.startswith("week"):
                delta = timedelta(weeks=amount)
            elif unit.startswith("month"):
                # Approximate months as 30 days — exact calendar math
                # isn't worth the dependency; HR queries work at
                # month-granularity.
                delta = timedelta(days=amount * 30)
            elif unit.startswith("year"):
                delta = timedelta(days=amount * 365)
            else:  # pragma: no cover — regex restricts to the above units
                return None, None
            date_from = now - delta
            spans.append((*span_tuple, f"date_from=last_{amount}_{unit}"))
            return date_from, None

        if m := self._DATE_SINCE_YEAR.search(query):
            year = int(m.group(1))
            # Only accept plausible years (avoid "since 1000" noise).
            if 1970 <= year <= now.year + 1:
                date_from = datetime(year, 1, 1, tzinfo=UTC)
                spans.append((m.start(), m.end(), f"date_from={year}-01-01"))
                return date_from, None

        if m := self._DATE_AFTER_ISO.search(query):
            try:
                date_from = datetime.fromisoformat(m.group(1)).replace(tzinfo=UTC)
                spans.append((m.start(), m.end(), f"date_from={m.group(1)}"))
                return date_from, None
            except ValueError:
                pass

        return None, None


class NullQueryParser:
    """Emits empty filters for every query.

    Used where ``SearchService`` is constructed without a real parser
    — primarily legacy tests. Production always uses
    ``HeuristicQueryParser`` via the composition root.
    """

    def parse(self, query: str) -> QueryIntent:
        return QueryIntent(raw_query=query, filters=ParsedFilters(), matched_spans=())
