"""Ollama LLM provider — local models."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import AsyncIterator

import httpx


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

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        payload = {
            "model": self._model,
            "system": system,
            "prompt": user,
            "stream": True,
        }
        # read=None: streaming means the connection stays open while
        # tokens arrive; a per-read timeout would abort mid-answer.
        timeout = httpx.Timeout(120.0, read=None)
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream("POST", self._url, json=payload) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                body = json.loads(line)
                chunk = body.get("response")
                if chunk:
                    yield chunk
                if body.get("done"):
                    break

    @property
    def model_name(self) -> str:
        return self._model
