"""Contextualizer factory.

Picks an implementation based on ``settings.contextualizer_provider``
and wires it to the configured ``LlmProvider``. If contextualization
is requested but no LlmProvider is available, silently falls back to
the null contextualizer — the rest of the pipeline keeps working,
just without the contextual-retrieval signal.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.adapters.protocols import ChunkContextualizer

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


def get_contextualizer(settings: Settings) -> ChunkContextualizer:
    name = settings.contextualizer_provider.lower()

    if name == "none":
        from app.adapters.contextualizers.null import NullChunkContextualizer

        return NullChunkContextualizer()

    if name == "llm":
        llm = _build_llm_for_contextualizer(settings)
        if llm is None:
            logger.warning(
                "contextualizer_provider=llm but no LlmProvider available; "
                "disabling contextualization"
            )
            from app.adapters.contextualizers.null import NullChunkContextualizer

            return NullChunkContextualizer()

        from app.adapters.contextualizers.llm import LlmChunkContextualizer

        return LlmChunkContextualizer(
            llm=llm,
            mode=settings.contextualizer_mode,
            full_doc_max_chars=settings.contextualizer_full_doc_max_chars,
        )

    raise ValueError(f"Unknown contextualizer_provider {name!r}. Expected: none, llm.")


def _build_llm_for_contextualizer(settings: Settings):
    """Build the LlmProvider for contextualization.

    Supports ``contextualizer_model`` as an override of ``llm_model``
    so the RAG model (often Sonnet) and the contextualization model
    (typically Haiku, cheaper + faster) can differ.
    """
    from app.adapters.llm.registry import get_llm_provider

    override = settings.contextualizer_model
    if not override:
        return get_llm_provider(settings)

    # Clone-ish: construct a shim settings with the override as
    # llm_model so the existing registry builds the right provider.
    class _SettingsShim:
        def __init__(self, base: Settings, model: str) -> None:
            self._base = base
            self.llm_model = model

        def __getattr__(self, name: str):
            return getattr(self._base, name)

    return get_llm_provider(_SettingsShim(settings, override))  # type: ignore[arg-type]
