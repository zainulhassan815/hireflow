"""Runtime vision-provider factory.

Called at task execution time (not import time) so the provider can be
switched via config without restarting the worker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.protocols import VisionProvider

if TYPE_CHECKING:
    from app.core.config import Settings


def get_vision_provider(settings: Settings) -> VisionProvider:
    """Instantiate the vision provider indicated by ``settings.vision_provider``.

    Providers are imported lazily so missing optional deps (pytesseract,
    anthropic, etc.) only error when that specific provider is selected.
    """
    name = settings.vision_provider.lower()

    if name == "claude":
        from app.adapters.vision.claude import ClaudeVisionProvider

        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is required when vision_provider=claude"
            )
        return ClaudeVisionProvider(
            api_key=settings.anthropic_api_key,
            model=settings.vision_model or "claude-sonnet-4-5-20250514",
        )

    if name == "ollama":
        from app.adapters.vision.ollama import OllamaVisionProvider

        return OllamaVisionProvider(
            base_url=settings.ollama_base_url,
            model=settings.vision_model or "llava:13b",
        )

    if name == "tesseract":
        from app.adapters.vision.tesseract import TesseractVisionProvider

        return TesseractVisionProvider()

    if name == "none":
        return _NullVisionProvider()

    raise ValueError(
        f"Unknown vision_provider {name!r}. Expected: claude, ollama, tesseract, none."
    )


class _NullVisionProvider:
    """No-op provider when OCR is disabled."""

    def extract_text_from_image(
        self, image: bytes, *, prompt: str | None = None
    ) -> str:
        return ""
