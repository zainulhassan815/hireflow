"""Ollama vision provider — local multimodal models (LLaVA, Llama Vision, etc.)."""

from __future__ import annotations

import base64
import json
import urllib.request

_DEFAULT_PROMPT = (
    "Extract all text from this image. Preserve the original structure, "
    "headings, and formatting as closely as possible. "
    "Return only the extracted text, no commentary."
)


class OllamaVisionProvider:
    """Uses the Ollama /api/generate endpoint with image support.

    No third-party HTTP client needed — stdlib urllib is sufficient for
    a single synchronous request from a Celery worker.
    """

    def __init__(self, *, base_url: str, model: str) -> None:
        self._url = f"{base_url.rstrip('/')}/api/generate"
        self._model = model

    def extract_text_from_image(
        self, image: bytes, *, prompt: str | None = None
    ) -> str:
        b64 = base64.standard_b64encode(image).decode("ascii")

        payload = json.dumps(
            {
                "model": self._model,
                "prompt": prompt or _DEFAULT_PROMPT,
                "images": [b64],
                "stream": False,
            }
        ).encode()

        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read())

        return body.get("response", "").strip()
