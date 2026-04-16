"""Runtime classifier factory.

Builds a classifier chain: rule-based first, LLM fallback if confidence
is below threshold. Called at task execution time for runtime flexibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.classifiers.composite import CompositeClassifier
from app.adapters.classifiers.rule_based import RuleBasedClassifier
from app.adapters.protocols import DocumentClassifier

if TYPE_CHECKING:
    from app.core.config import Settings


def get_document_classifier(settings: Settings) -> DocumentClassifier:
    """Build the classifier chain based on config.

    - If an LLM provider is available (vision_provider = claude|ollama),
      the LLM classifier acts as fallback for low-confidence rule-based results.
    - Otherwise, rule-based only.
    """
    rule_based = RuleBasedClassifier()

    provider = settings.vision_provider.lower()
    if provider in ("claude", "ollama"):
        from app.adapters.classifiers.llm import (
            LlmClassifier,
            create_claude_llm_call,
            create_ollama_llm_call,
        )

        if provider == "claude" and settings.anthropic_api_key:
            model = settings.vision_model or "claude-sonnet-4-5-20250514"
            llm_call = create_claude_llm_call(
                settings.anthropic_api_key.get_secret_value(), model
            )
            return CompositeClassifier(rule_based, LlmClassifier(llm_call))

        if provider == "ollama":
            model = settings.vision_model or "llava:13b"
            llm_call = create_ollama_llm_call(settings.ollama_base_url, model)
            return CompositeClassifier(rule_based, LlmClassifier(llm_call))

    return rule_based
