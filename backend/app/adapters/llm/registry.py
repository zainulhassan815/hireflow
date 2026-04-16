"""Runtime LLM provider factory.

Shares the same config keys as the vision provider (``llm_provider``,
``anthropic_api_key``, ``ollama_base_url``) so operators configure one
provider and it serves vision, classification, and RAG.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.protocols import LlmProvider

if TYPE_CHECKING:
    from app.core.config import Settings


def get_llm_provider(settings: Settings) -> LlmProvider | None:
    """Return the configured LLM provider, or None if unavailable."""
    name = settings.llm_provider.lower()

    if name == "anthropic":
        if not settings.anthropic_api_key:
            return None
        from app.adapters.llm.claude import ClaudeLlmProvider

        return ClaudeLlmProvider(
            api_key=settings.anthropic_api_key,
            model=settings.vision_model or "claude-sonnet-4-5-20250514",
        )

    if name == "ollama":
        from app.adapters.llm.ollama import OllamaLlmProvider

        return OllamaLlmProvider(
            base_url=settings.ollama_base_url,
            model=settings.vision_model or "llama3:8b",
        )

    return None
