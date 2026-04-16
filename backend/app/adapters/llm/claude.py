"""Claude LLM provider."""

from __future__ import annotations

import anthropic
from pydantic import SecretStr


class ClaudeLlmProvider:
    def __init__(
        self, *, api_key: SecretStr, model: str, max_tokens: int = 4096
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key.get_secret_value())
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

    @property
    def model_name(self) -> str:
        return self._model
