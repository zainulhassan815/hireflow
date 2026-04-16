"""Runtime LLM provider factory.

Uses ``llm_provider`` and ``llm_model`` from settings. Each provider
type has its own sensible default model if ``llm_model`` isn't set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.protocols import LlmProvider

if TYPE_CHECKING:
    from app.core.config import Settings

_OLLAMA_DEFAULT_MODEL = "llama3:8b"


def get_llm_provider(settings: Settings) -> LlmProvider | None:
    """Return the configured LLM provider, or None if unavailable."""
    name = settings.llm_provider.lower()

    if name == "anthropic":
        if not settings.anthropic_api_key:
            return None
        from app.adapters.llm.claude import ClaudeLlmProvider

        return ClaudeLlmProvider(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
        )

    if name == "ollama":
        from app.adapters.llm.ollama import OllamaLlmProvider

        return OllamaLlmProvider(
            base_url=settings.ollama_base_url,
            model=settings.llm_model
            if settings.llm_provider == "ollama"
            else _OLLAMA_DEFAULT_MODEL,
        )

    return None
