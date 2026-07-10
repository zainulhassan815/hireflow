"""F45.d/e/f — required-skill floor, explainability, cold-start flag.

The scoring signals are pure functions of a Job + Candidate, so they're
exercised directly (no DB / no mocks — there is no IO to mock).
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.models import Candidate, Job
from app.services.matching_service import MatchingService


def _job(**kw) -> Job:
    kw.setdefault("required_skills", ["python", "aws"])
    kw.setdefault("preferred_skills", [])
    kw.setdefault("experience_min", 3)
    kw.setdefault("experience_max", 7)
    return Job(title="Cloud Engineer", description="d", **kw)


def _candidate(**kw) -> Candidate:
    kw.setdefault("skills", ["python"])
    kw.setdefault("experience_years", 4)
    kw.setdefault("attachments", [])
    return Candidate(**kw)


# ---------- F45.d required-skill floor ----------


def test_partial_policy_is_default_and_gives_fraction(monkeypatch) -> None:
    monkeypatch.setattr(settings, "matching_required_skill_policy", "partial")
    # 1 of 2 required matched, no preferred → 0.7 * 0.5 = 0.35
    score = MatchingService._skill_overlap(_job(), _candidate(skills=["python"]))
    assert score == pytest.approx(0.35)


def test_zero_policy_gates_skill_signal_on_required_miss(monkeypatch) -> None:
    monkeypatch.setattr(settings, "matching_required_skill_policy", "zero")
    score = MatchingService._skill_overlap(_job(), _candidate(skills=["python"]))
    assert score == 0.0


def test_halve_policy_scales_on_required_miss(monkeypatch) -> None:
    monkeypatch.setattr(settings, "matching_required_skill_policy", "halve")
    score = MatchingService._skill_overlap(_job(), _candidate(skills=["python"]))
    assert score == pytest.approx(0.175)


@pytest.mark.parametrize("policy", ["partial", "zero", "halve"])
def test_full_required_match_is_unaffected_by_policy(monkeypatch, policy) -> None:
    monkeypatch.setattr(settings, "matching_required_skill_policy", policy)
    score = MatchingService._skill_overlap(_job(), _candidate(skills=["python", "aws"]))
    assert score == pytest.approx(0.7)


# ---------- F45.f cold-start ----------


def test_empty_skills_candidate_is_flagged_unscored() -> None:
    svc = MatchingService(None, None, None, None)
    breakdown = svc._breakdown(_job(), _candidate(skills=[]), {})
    assert breakdown["unscored"] is True


def test_skilled_candidate_is_not_unscored() -> None:
    svc = MatchingService(None, None, None, None)
    breakdown = svc._breakdown(_job(), _candidate(skills=["python"]), {})
    assert breakdown["unscored"] is False


# ---------- F45.e explainability ----------


def test_explanation_mentions_matched_skills_and_experience() -> None:
    text = MatchingService._explanation(
        _job(),
        _candidate(skills=["python", "aws"], experience_years=4),
        skill=0.7,
        experience=1.0,
        vector=0.7,
        credential=0.0,
    )
    assert "required" in text.lower()
    assert "python" in text.lower()
    assert "4 yrs" in text.lower()
    assert "similarity" in text.lower()
    assert text.endswith(".")


def test_explanation_flags_missing_skills() -> None:
    text = MatchingService._explanation(
        _job(),
        _candidate(skills=[], experience_years=None),
        skill=0.0,
        experience=0.3,
        vector=0.5,
        credential=0.0,
    )
    assert "no skills extracted" in text.lower()


def test_explanation_notes_credentials_when_present() -> None:
    text = MatchingService._explanation(
        _job(),
        _candidate(),
        skill=0.5,
        experience=1.0,
        vector=0.4,
        credential=0.5,
    )
    assert "credential" in text.lower()
