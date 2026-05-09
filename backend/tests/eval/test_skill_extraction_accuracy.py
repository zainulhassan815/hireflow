"""F103.b — LLM skill-extraction accuracy eval.

Hits the real LLM classifier (Claude or Ollama, per
``LLM_PROVIDER`` / ``ANTHROPIC_API_KEY`` settings) against a small
labeled set of resume bodies. Reports per-fixture recall + the overall
micro-recall on the ``expected_skills`` set, fails below
``LLM_SKILL_RECALL_THRESHOLD``.

Skipped when no LLM provider is configured — this eval is for guarding
the prompt against regressions, not a hard CI requirement.

Run with ``make eval-skill-extraction``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.classifiers.llm import LlmClassifier
from app.core.config import settings

# Recall, not F1. False positives from the LLM (e.g., picking up an
# adjacent tech that wasn't in our expected list) are usually fine for
# downstream search/match — we only care that the *expected* skills
# are recovered.
LLM_SKILL_RECALL_THRESHOLD = 0.80


def _build_llm_classifier() -> LlmClassifier | None:
    provider = settings.llm_provider.lower()
    if provider == "anthropic" and settings.anthropic_api_key:
        from app.adapters.classifiers.llm import create_claude_llm_call

        return LlmClassifier(
            create_claude_llm_call(
                settings.anthropic_api_key.get_secret_value(), settings.llm_model
            )
        )
    if provider == "ollama":
        from app.adapters.classifiers.llm import create_ollama_llm_call

        return LlmClassifier(
            create_ollama_llm_call(settings.ollama_base_url, settings.llm_model)
        )
    return None


def _load_cases() -> list[dict]:
    path = Path(__file__).parent / "skill_extraction_cases.json"
    with path.open() as f:
        cases = json.load(f)
    assert isinstance(cases, list) and cases
    return cases


def test_llm_skill_extraction_recall() -> None:
    classifier = _build_llm_classifier()
    if classifier is None:
        pytest.skip("no LLM provider configured (set LLM_PROVIDER + key)")

    cases = _load_cases()

    total_expected = 0
    total_recovered = 0
    per_case_lines: list[str] = []

    for case in cases:
        result = classifier.classify(case["text"], case["filename"])
        actual = {s.lower() for s in (result.metadata.get("skills") or [])}
        expected = {s.lower() for s in case["expected_skills"]}
        recovered = expected & actual
        missed = expected - actual

        total_expected += len(expected)
        total_recovered += len(recovered)

        bar = "#" * int(20 * len(recovered) / max(len(expected), 1))
        per_case_lines.append(
            f"  {case['name']:<36} {bar:<20} "
            f"{len(recovered)}/{len(expected)}   missed={sorted(missed) or '-'}"
        )

    overall = total_recovered / max(total_expected, 1)
    print("\nLLM skill-extraction eval")
    print(f"  overall recall: {overall:.2%} ({total_recovered}/{total_expected})")
    for line in per_case_lines:
        print(line)

    assert overall >= LLM_SKILL_RECALL_THRESHOLD, (
        f"LLM skill recall {overall:.2%} below threshold "
        f"{LLM_SKILL_RECALL_THRESHOLD:.0%}"
    )
