"""Ollama LLM provider — local models."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import AsyncIterator

import httpx

from app.domain.exceptions import (
    LlmProviderError,
    LlmRateLimited,
    LlmTimeout,
    LlmUnavailable,
)


def _translate_httpx_error(exc: Exception) -> LlmProviderError:
    """Map an httpx (or json-decode) error onto the domain taxonomy."""
    if isinstance(exc, httpx.TimeoutException):
        return LlmTimeout("Ollama timed out.")
    if isinstance(exc, httpx.ConnectError):
        return LlmUnavailable("Cannot reach Ollama.")
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 429:
            return LlmRateLimited()
        return LlmUnavailable("Ollama returned an error response.")
    if isinstance(exc, json.JSONDecodeError | httpx.RequestError):
        return LlmUnavailable("Ollama returned malformed data.")
    raise exc


def _translate_urllib_error(exc: Exception) -> LlmProviderError:
    """Same mapping for the sync urllib path used by Celery workers."""
    if isinstance(exc, TimeoutError):
        return LlmTimeout("Ollama timed out.")
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
        return LlmRateLimited()
    if isinstance(exc, urllib.error.URLError):
        return LlmUnavailable("Cannot reach Ollama.")
    if isinstance(exc, json.JSONDecodeError):
        return LlmUnavailable("Ollama returned malformed JSON.")
    raise exc


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
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise _translate_urllib_error(exc) from exc
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
        try:
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
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise _translate_httpx_error(exc) from exc

    @property
    def model_name(self) -> str:
        return self._model
