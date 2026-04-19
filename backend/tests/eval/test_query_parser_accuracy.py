"""F89.a — query-parser accuracy eval.

Runs ``HeuristicQueryParser`` against a labeled set and reports
per-field F1. Fails below ``QUERY_PARSER_F1_THRESHOLD``. Operator-
facing: the printed scorecard + misclassification list tells you
exactly where to add canonicals (``intent_canonicals.py``-style) or
fix labels.

Run with ``make eval-parser``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

QUERY_PARSER_F1_THRESHOLD = 0.85


def _load_cases() -> list[dict]:
    path = Path(__file__).parent / "query_parser_cases.json"
    with path.open() as f:
        cases = json.load(f)
    assert isinstance(cases, list) and cases
    return cases


def _expected_date_from(case: dict) -> datetime | None:
    if "date_from_year" in case:
        return datetime(case["date_from_year"], 1, 1, tzinfo=UTC)
    if "date_from_iso" in case:
        return datetime.fromisoformat(case["date_from_iso"]).replace(tzinfo=UTC)
    if "date_from_months_ago" in case:
        return datetime.now(UTC) - timedelta(days=case["date_from_months_ago"] * 30)
    return None


def _dates_approx_equal(a: datetime | None, b: datetime | None) -> bool:
    """Allow ±15 days slack for relative-date parsing.

    Months are approximated as 30 days and years as 365 days (no
    calendar library to avoid the dep), so a 2-year query drifts by
    ~10 days from exact. 15 days is enough tolerance for that while
    still catching obvious extraction errors (wrong year, wrong
    magnitude).
    """
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs((a - b).total_seconds()) < 15 * 86400


def test_query_parser_accuracy(capsys) -> None:
    from app.services.query_parser import HeuristicQueryParser
    from app.services.query_parser_vocab import (
        DOCUMENT_TYPE_KEYWORDS,
        KNOWN_SKILLS,
        SENIORITY_THRESHOLDS,
    )

    parser = HeuristicQueryParser(
        seniority=SENIORITY_THRESHOLDS,
        skills=KNOWN_SKILLS,
        document_types=DOCUMENT_TYPE_KEYWORDS,
    )

    cases = _load_cases()
    # Per-field tally: {field: [tp, fp, fn]}
    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    misses: list[dict] = []

    for case in cases:
        intent = parser.parse(case["query"])
        got = intent.filters

        # skills (set comparison)
        want_skills = set(case.get("skills", []))
        got_skills = set(got.skills)
        tally["skills"][0] += len(want_skills & got_skills)
        tally["skills"][1] += len(got_skills - want_skills)
        tally["skills"][2] += len(want_skills - got_skills)

        # min_experience_years (scalar)
        want_years = case.get("min_experience_years")
        got_years = got.min_experience_years
        if want_years is not None and got_years == want_years:
            tally["min_experience_years"][0] += 1
        elif want_years is None and got_years is None:
            pass  # true negative; not counted
        elif got_years is not None and want_years != got_years:
            tally["min_experience_years"][1] += 1  # false positive
            if want_years is not None:
                tally["min_experience_years"][2] += 1  # also false negative
        elif want_years is not None and got_years is None:
            tally["min_experience_years"][2] += 1  # false negative

        # document_type (scalar)
        want_dt = case.get("document_type")
        got_dt = got.document_type
        if want_dt and got_dt == want_dt:
            tally["document_type"][0] += 1
        elif got_dt and got_dt != want_dt:
            tally["document_type"][1] += 1
            if want_dt:
                tally["document_type"][2] += 1
        elif want_dt and not got_dt:
            tally["document_type"][2] += 1

        # date_from (tolerant compare)
        want_date = _expected_date_from(case)
        got_date = got.date_from
        if want_date and _dates_approx_equal(want_date, got_date):
            tally["date_from"][0] += 1
        elif got_date and not _dates_approx_equal(want_date, got_date):
            tally["date_from"][1] += 1
            if want_date:
                tally["date_from"][2] += 1
        elif want_date and not got_date:
            tally["date_from"][2] += 1

        # track misses for operator triage
        per_case_wrong = (
            (want_skills != got_skills)
            or (want_years is not None and got_years != want_years)
            or (want_dt != got_dt)
            or (want_date and not _dates_approx_equal(want_date, got_date))
            or (got_years is not None and want_years is None)
            or (got_dt is not None and want_dt is None)
            or (got_date is not None and want_date is None)
        )
        if per_case_wrong:
            misses.append(
                {
                    "query": case["query"],
                    "expected": {
                        "skills": sorted(want_skills),
                        "years": want_years,
                        "doc_type": want_dt,
                        "date_from": want_date.isoformat() if want_date else None,
                    },
                    "got": {
                        "skills": sorted(got_skills),
                        "years": got_years,
                        "doc_type": got_dt,
                        "date_from": got_date.isoformat() if got_date else None,
                    },
                    "spans": list(intent.matched_spans),
                }
            )

    # Compute F1 per field, weighted average.
    def _f1(tp: int, fp: int, fn: int) -> float:
        if tp + fp == 0 and tp + fn == 0:
            return 1.0  # no signal, no loss
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    field_f1 = {field: _f1(*counts) for field, counts in tally.items()}
    overall = sum(field_f1.values()) / len(field_f1) if field_f1 else 0.0

    with capsys.disabled():
        print("\nQuery parser eval")
        print(f"  overall F1: {overall:.2%}")
        for field, (tp, fp, fn) in sorted(tally.items()):
            f1 = _f1(tp, fp, fn)
            bar = "#" * int(f1 * 14) + "." * (14 - int(f1 * 14))
            print(f"  {field:<22} {bar} F1={f1:.0%}  tp={tp} fp={fp} fn={fn}")
        if misses:
            print(f"\n  {len(misses)} cases with mismatches:")
            for m in misses[:10]:
                print(f"    Q: {m['query']!r}")
                print(f"       expected: {m['expected']}")
                print(f"       got     : {m['got']}")
            if len(misses) > 10:
                print(f"    ... and {len(misses) - 10} more")

    assert overall >= QUERY_PARSER_F1_THRESHOLD, (
        f"Query parser F1 {overall:.1%} below threshold "
        f"{QUERY_PARSER_F1_THRESHOLD:.1%}. Review mismatches above, "
        f"add vocabulary in query_parser_vocab.py, or fix labels in "
        f"query_parser_cases.json."
    )
