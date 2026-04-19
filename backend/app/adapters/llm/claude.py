"""Claude LLM provider."""

from __future__ import annotations

from collections.abc import AsyncIterator

import anthropic
from pydantic import SecretStr


class ClaudeLlmProvider:
    def __init__(
        self, *, api_key: SecretStr, model: str, max_tokens: int = 4096
    ) -> None:
        key = api_key.get_secret_value()
        # Two clients: sync for Celery workers (classifiers) and async
        # for streaming inside FastAPI routes. Sharing one client across
        # both contexts would require nested event loops or thread
        # bridging — both workarounds.
        self._client = anthropic.Anthropic(api_key=key)
        self._async_client = anthropic.AsyncAnthropic(api_key=key)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        async with self._async_client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    @property
    def model_name(self) -> str:
        return self._model
