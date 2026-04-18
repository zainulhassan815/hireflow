"""Unit tests for the F92.1 highlight helper.

Pure-function tests, no fixtures needed.
"""

from __future__ import annotations

from app.services.highlight import (
    _merge_overlaps,
    extract_query_terms,
    find_match_spans,
)

# ---------- extract_query_terms ----------


def test_extract_query_terms_lowercases_and_dedups() -> None:
    assert extract_query_terms("Python python PYTHON") == ["python"]


def test_extract_query_terms_drops_stopwords_and_short_tokens() -> None:
    assert extract_query_terms("a developer with the skills in python") == [
        "developer",
        "skills",
        "python",
    ]


def test_extract_query_terms_keeps_special_char_tokens() -> None:
    # c++, c#, .net are real skill terms — must survive tokenization.
    terms = extract_query_terms("Looking for C++ and C# and .NET engineer")
    assert "c++" in terms
    assert "c#" in terms
    assert ".net" in terms


def test_extract_query_terms_empty() -> None:
    assert extract_query_terms("") == []
    assert extract_query_terms("   ") == []
    assert extract_query_terms("a the of") == []


# ---------- find_match_spans ----------


def test_find_match_spans_case_insensitive() -> None:
    spans = find_match_spans("Python developer with PYTHON skills", ["python"])
    assert spans == [(0, 6), (22, 28)]


def test_find_match_spans_word_boundary_for_alphanumeric() -> None:
    # "java" must not match inside "javascript".
    spans = find_match_spans("javascript and java are different", ["java"])
    assert spans == [(15, 19)]


def test_find_match_spans_special_char_terms_use_substring() -> None:
    # \b doesn't help for c++ — fall back to substring.
    spans = find_match_spans("c++ developer for c++ projects", ["c++"])
    assert spans == [(0, 3), (18, 21)]


def test_find_match_spans_merges_overlapping_matches() -> None:
    # "python" and "py" both match — overlapping spans collapse.
    spans = find_match_spans("python", ["python", "py"])
    assert spans == [(0, 6)]


def test_find_match_spans_no_terms_returns_empty() -> None:
    assert find_match_spans("any text", []) == []


def test_find_match_spans_no_text_returns_empty() -> None:
    assert find_match_spans("", ["python"]) == []


def test_find_match_spans_no_matches() -> None:
    assert find_match_spans("nothing relevant here", ["python", "java"]) == []


# ---------- _merge_overlaps ----------


def test_merge_overlaps_disjoint_preserves_order() -> None:
    assert _merge_overlaps([(0, 3), (10, 14)]) == [(0, 3), (10, 14)]


def test_merge_overlaps_adjacent_collapses() -> None:
    assert _merge_overlaps([(0, 5), (5, 10)]) == [(0, 10)]


def test_merge_overlaps_unsorted_input_sorts_first() -> None:
    assert _merge_overlaps([(10, 14), (0, 3)]) == [(0, 3), (10, 14)]


# ---------- end-to-end roundtrip ----------


def test_roundtrip_python_engineer_query() -> None:
    text = "Senior Python engineer with FastAPI and Kubernetes experience."
    terms = extract_query_terms("python engineer kubernetes")
    spans = find_match_spans(text, terms)
    # Verify the substrings actually highlight what we expect.
    highlighted = [text[s:e].lower() for s, e in spans]
    assert highlighted == ["python", "engineer", "kubernetes"]
