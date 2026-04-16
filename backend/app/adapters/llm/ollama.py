"""Ollama LLM provider — local models."""

from __future__ import annotations

import json
import urllib.request


class OllamaLlmProvider:
    def __init__(self, *, base_url: str, model: str) -> None:
        self._url = f"{base_url.rstrip('/')}/api/generate"
        self._model = model

    def complete(self, system: str, user: str) -> str:
        payload = json.dumps(
            {
                "model": self._model,
                "system": system,
                "prompt": user,
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

    @property
    def model_name(self) -> str:
        return self._model
