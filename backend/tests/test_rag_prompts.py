"""F81.g — prompt-stack composition tests.

``build_system_prompt`` is a pure function; no model needed.
Exhaustiveness of ``FORMAT_RULES`` is asserted at import time in
``rag_prompts.py`` — this file locks in the *content* contracts.
"""

from __future__ import annotations

from typing import get_args

from app.services.intent_canonicals import Intent
from app.services.rag_prompts import (
    EVIDENCE_RULES,
    FEW_SHOT,
    FORMAT_RULES,
    IDENTITY,
    PROMPT_VERSION,
    build_system_prompt,
)

# ---------------------------------------------------------------------------
# Version + exhaustiveness
# ---------------------------------------------------------------------------


def test_prompt_version_is_set() -> None:
    assert PROMPT_VERSION and isinstance(PROMPT_VERSION, str)


def test_format_rules_cover_every_intent() -> None:
    """Adding a new ``Intent`` literal without a matching
    ``FormatRule`` would crash at query time with an AttributeError.
    Exhaustiveness check keeps the contract honest."""
    declared = set(get_args(Intent))
    assert set(FORMAT_RULES.keys()) == declared


def test_few_shot_keys_are_a_subset_of_format_rules() -> None:
    """FEW_SHOT is intentionally partial — only comparison + ranking
    today. If we add an intent to FEW_SHOT, it must already be a
    valid intent."""
    declared = set(get_args(Intent))
    assert set(FEW_SHOT.keys()).issubset(declared)
    # Lock in the specific subset so silent expansion surfaces in a
    # code review.
    assert set(FEW_SHOT.keys()) == {"comparison", "ranking"}


# ---------------------------------------------------------------------------
# Layer composition — general intent
# ---------------------------------------------------------------------------


def test_general_prompt_contains_identity_and_evidence_rules() -> None:
    prompt = build_system_prompt("general")
    # Identity layer present.
    assert "senior HR research assistant" in prompt
    # Evidence rules present.
    assert "Not in the provided documents." in prompt
    assert "square brackets" in prompt
    # Default word cap — general intent is the only one with 200.
    assert "200 words" in prompt
    # No few-shot for general.
    assert "Example:" not in prompt


# ---------------------------------------------------------------------------
# Per-intent format instructions present
# ---------------------------------------------------------------------------


def test_count_prompt_includes_count_format_directive() -> None:
    prompt = build_system_prompt("count")
    assert "number alone on its own line" in prompt
    assert "60 words" in prompt


def test_yes_no_prompt_instructs_yes_or_no_opener() -> None:
    prompt = build_system_prompt("yes_no")
    assert 'Start with "Yes" or "No"' in prompt
    assert "40 words" in prompt


def test_comparison_prompt_includes_table_directive_and_few_shot() -> None:
    prompt = build_system_prompt("comparison")
    assert "markdown table" in prompt
    assert "Source" in prompt  # Source column requirement
    # Few-shot example present — without it, Haiku drifts to prose.
    assert "Example:" in prompt
    assert "| React |" in prompt


def test_ranking_prompt_includes_ordered_list_directive_and_few_shot() -> None:
    prompt = build_system_prompt("ranking")
    assert "ordered list" in prompt
    assert "Example:" in prompt
    assert "1. Alice Ng" in prompt


def test_timeline_uses_markdown_table_without_word_cap() -> None:
    prompt = build_system_prompt("timeline")
    assert "markdown table" in prompt
    # Table-shaped intents skip the word cap — structure enforces tightness.
    assert "Keep the answer under" not in prompt


# ---------------------------------------------------------------------------
# Layer order — identity first, few-shot last
# ---------------------------------------------------------------------------


def test_identity_precedes_evidence_rules_precedes_format() -> None:
    prompt = build_system_prompt("count")
    idx_identity = prompt.find("senior HR research assistant")
    idx_evidence = prompt.find("Evidence rules:")
    idx_format = prompt.find("Format:")
    assert 0 <= idx_identity < idx_evidence < idx_format


def test_few_shot_lands_at_the_end_for_comparison() -> None:
    prompt = build_system_prompt("comparison")
    idx_format = prompt.find("Format:")
    idx_example = prompt.find("Example:")
    # Few-shot comes after the format instruction so the exemplar is
    # the last thing the model reads before the user message.
    assert idx_format < idx_example


# ---------------------------------------------------------------------------
# Sanity — content we don't want leaking across layers
# ---------------------------------------------------------------------------


def test_evidence_rules_do_not_contain_format_hints() -> None:
    """Evidence rules should be intent-agnostic. A table directive
    leaking in would effectively force every answer to be a table."""
    assert "markdown table" not in EVIDENCE_RULES
    assert "ordered list" not in EVIDENCE_RULES
    assert "bulleted list" not in EVIDENCE_RULES


def test_identity_is_a_single_paragraph() -> None:
    # Identity should be terse — one paragraph, not a page.
    stripped = IDENTITY.strip()
    assert "\n\n" not in stripped, "IDENTITY grew to multiple paragraphs"
