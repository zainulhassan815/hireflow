"""F89.a — HeuristicQueryParser unit tests.

Per-extractor tests (parametrized) cover the regex + vocabulary
patterns; composite tests cover multi-filter queries and conflict
resolution. No embedder, no DB — the parser is a pure function of
query string + vocabularies.

The eval harness (``tests/eval/test_query_parser_accuracy.py``) runs
the same parser over 60+ labeled queries and reports per-field F1;
that's the precision/recall number. These unit tests lock in
specific behaviors so a refactor doesn't silently regress them.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services.query_parser import HeuristicQueryParser, NullQueryParser
from app.services.query_parser_vocab import (
    DOCUMENT_TYPE_KEYWORDS,
    KNOWN_SKILLS,
    SENIORITY_THRESHOLDS,
)


@pytest.fixture
def parser() -> HeuristicQueryParser:
    return HeuristicQueryParser(
        seniority=SENIORITY_THRESHOLDS,
        skills=KNOWN_SKILLS,
        document_types=DOCUMENT_TYPE_KEYWORDS,
    )


# ---------------------------------------------------------------------------
# Year extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("5+ years Python", 5),
        ("at least 3 years experience", 3),
        ("over 10 yrs", 10),
        ("more than 7 years", 7),
        ("5-10 years experience", 5),  # lower bound wins
        ("3 years of experience", 3),
        ("developer with 8 years experience", 8),
    ],
)
def test_year_extraction_positive_cases(
    parser: HeuristicQueryParser, query: str, expected: int
) -> None:
    result = parser.parse(query)
    assert result.filters.min_experience_years == expected


@pytest.mark.parametrize(
    "query",
    [
        "",
        "random text with no numbers",
        "2025 candidates in the pool",  # no "years"/"experience" context
    ],
)
def test_year_extraction_negative_cases(
    parser: HeuristicQueryParser, query: str
) -> None:
    result = parser.parse(query)
    assert result.filters.min_experience_years is None


# ---------------------------------------------------------------------------
# Seniority → year threshold
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("senior developer", 5),
        ("sr. engineer", 5),
        ("mid-level backend", 3),
        ("junior candidate", 1),
        ("jr frontend", 1),
        ("principal architect", 8),
        ("staff engineer", 7),
        ("lead developer", 7),
        ("intern resume", 0),
    ],
)
def test_seniority_maps_to_year_threshold(
    parser: HeuristicQueryParser, query: str, expected: int
) -> None:
    result = parser.parse(query)
    assert result.filters.min_experience_years == expected


def test_explicit_years_beats_seniority(parser: HeuristicQueryParser) -> None:
    """F89.a precedence rule: explicit year count always wins over
    the seniority token's implicit threshold."""
    result = parser.parse("senior developer with 10 years experience")
    assert result.filters.min_experience_years == 10


def test_seniority_fires_only_without_explicit_years(
    parser: HeuristicQueryParser,
) -> None:
    result = parser.parse("senior developer")
    assert result.filters.min_experience_years == 5


# ---------------------------------------------------------------------------
# Skill extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("python developer", {"python"}),
        ("Python Developer", {"python"}),  # case-insensitive
        ("react and angular", {"react", "angular"}),
        ("machine learning engineer", {"machine learning"}),  # multi-word
        ("AWS with kubernetes", {"aws", "kubernetes"}),
        ("c++ developer", {"c++"}),
        ("node.js and typescript", {"node.js", "typescript"}),
        (".net backend", {".net"}),
    ],
)
def test_skill_extraction_positive_cases(
    parser: HeuristicQueryParser, query: str, expected: set[str]
) -> None:
    result = parser.parse(query)
    assert set(result.filters.skills) == expected


@pytest.mark.parametrize(
    "query",
    [
        "learning about something",  # "learning" alone isn't a skill
        "go fast today",  # "go" isn't in the curated vocab (ambiguous)
        "random prose with no tech terms",
    ],
)
def test_skill_extraction_negative_cases(
    parser: HeuristicQueryParser, query: str
) -> None:
    result = parser.parse(query)
    assert result.filters.skills == ()


def test_longest_match_wins_for_multi_word_skills(
    parser: HeuristicQueryParser,
) -> None:
    """When "machine learning" is a skill and "learning" is not, the
    longer multi-word match should win and "learning" shouldn't
    double-count."""
    result = parser.parse("machine learning and tensorflow")
    assert set(result.filters.skills) == {"machine learning", "tensorflow"}


def test_skill_boundary_rejects_substring_in_word(
    parser: HeuristicQueryParser,
) -> None:
    """The custom boundary check must reject "c++" inside a word —
    only match when surrounded by non-alphanumeric characters or
    string boundaries."""
    # "abc++def" has alphanumeric chars on both sides of "c++" — no match.
    result = parser.parse("abc++def filename")
    assert "c++" not in result.filters.skills


def test_skill_boundary_accepts_punctuated_surroundings(
    parser: HeuristicQueryParser,
) -> None:
    """But "c++ developer" and "(c++)" should both match — non-
    alphanumeric surroundings or string boundaries are the rule."""
    assert "c++" in set(parser.parse("c++ developer").filters.skills)
    assert "c++" in set(parser.parse("(c++) with 5 years").filters.skills)


# ---------------------------------------------------------------------------
# Document type extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("resume with AWS", "resume"),
        ("Resumes for Python", "resume"),
        ("CV of Alice", "resume"),
        ("show me CVs", "resume"),
        ("job description for backend", "job_description"),
        ("JD for senior role", "job_description"),
        ("role description", "job_description"),
        ("letter of recommendation", "letter"),
    ],
)
def test_document_type_extraction(
    parser: HeuristicQueryParser, query: str, expected: str
) -> None:
    result = parser.parse(query)
    assert result.filters.document_type == expected


def test_document_type_absent_when_no_keyword(
    parser: HeuristicQueryParser,
) -> None:
    result = parser.parse("candidates with Python")
    assert result.filters.document_type is None


# ---------------------------------------------------------------------------
# Date extraction
# ---------------------------------------------------------------------------


def test_relative_date_last_years(parser: HeuristicQueryParser) -> None:
    result = parser.parse("candidates from last 2 years")
    assert result.filters.date_from is not None
    now = datetime.now(UTC)
    delta = now - result.filters.date_from
    # 2 years ~= 730 days; tolerate ±5 days for test timing.
    assert 720 <= delta.days <= 740


def test_since_year_date(parser: HeuristicQueryParser) -> None:
    result = parser.parse("candidates since 2020")
    assert result.filters.date_from == datetime(2020, 1, 1, tzinfo=UTC)


def test_after_iso_date(parser: HeuristicQueryParser) -> None:
    result = parser.parse("applicants after 2024-01-15")
    assert result.filters.date_from == datetime(2024, 1, 15, tzinfo=UTC)


def test_implausible_year_rejected(parser: HeuristicQueryParser) -> None:
    """'since 1000' is almost certainly not a meaningful filter —
    bail rather than send a query for rows older than Postgres."""
    result = parser.parse("candidates since 1000")
    assert result.filters.date_from is None


# ---------------------------------------------------------------------------
# Composite queries
# ---------------------------------------------------------------------------


def test_composite_query_extracts_multiple_filters(
    parser: HeuristicQueryParser,
) -> None:
    """The canonical 'biggest win' query from the F89.a motivation
    — all filter types present and extracted correctly."""
    result = parser.parse(
        "5+ years senior Python developer with AWS from last 6 months"
    )
    assert result.filters.min_experience_years == 5  # explicit beats seniority
    assert set(result.filters.skills) == {"python", "aws"}
    assert result.filters.date_from is not None


def test_matched_spans_populated_for_observability(
    parser: HeuristicQueryParser,
) -> None:
    """Operators grep logs for 'matched_spans=' to diagnose bad
    parses. The list must contain one entry per claimed token."""
    result = parser.parse("5+ years Python developer")
    kinds = {span[2].split("=")[0] for span in result.matched_spans}
    assert "years" in kinds
    assert "skill" in kinds


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_query_returns_empty_filters(parser: HeuristicQueryParser) -> None:
    result = parser.parse("")
    assert result.filters.is_empty
    assert result.matched_spans == ()


def test_whitespace_only_returns_empty_filters(
    parser: HeuristicQueryParser,
) -> None:
    result = parser.parse("   \t\n  ")
    assert result.filters.is_empty


def test_pure_semantic_query_has_empty_filters(
    parser: HeuristicQueryParser,
) -> None:
    """Queries without any structured tokens should emit empty
    filters — this preserves the F81.k default (no SQL path for
    retrieve_chunks)."""
    result = parser.parse("candidates who are resilient problem solvers")
    assert result.filters.is_empty


# ---------------------------------------------------------------------------
# NullQueryParser (default for SearchService when no real parser injected)
# ---------------------------------------------------------------------------


def test_null_parser_always_returns_empty() -> None:
    null = NullQueryParser()
    for q in ["5+ years Python", "senior engineer", "anything at all"]:
        result = null.parse(q)
        assert result.filters.is_empty
        assert result.raw_query == q
