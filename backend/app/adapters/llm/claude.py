"""Claude LLM provider."""

from __future__ import annotations

from collections.abc import AsyncIterator

import anthropic
from pydantic import SecretStr

from app.domain.exceptions import (
    LlmProviderError,
    LlmRateLimited,
    LlmTimeout,
    LlmUnavailable,
)


def _parse_retry_after(response: object | None) -> int | None:
    """Integer seconds from a ``Retry-After`` header, or None.

    Per RFC 7231 §7.1.3 the header may also be an HTTP-date; that form
    is not parsed — we fail loudly by returning None rather than ship
    speculative date-parsing that might mis-round in production. Every
    Claude response I've seen uses the integer form.
    """
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _translate_anthropic_error(exc: anthropic.APIError) -> LlmProviderError:
    """Map an Anthropic SDK exception onto the domain taxonomy.

    Only the exception types we explicitly handle are mapped — unknown
    SDK errors propagate to the caller as-is, where RagService's
    last-resort ``except Exception`` logs the full traceback.
    """
    if isinstance(exc, anthropic.RateLimitError):
        return LlmRateLimited(
            retry_after_seconds=_parse_retry_after(exc.response),
        )
    if isinstance(exc, anthropic.APITimeoutError):
        return LlmTimeout("AI provider timed out.")
    if isinstance(
        exc,
        anthropic.APIConnectionError
        | anthropic.AuthenticationError
        | anthropic.PermissionDeniedError
        | anthropic.InternalServerError,
    ):
        return LlmUnavailable("Cannot reach the AI provider.")
    # BadRequestError, NotFoundError, UnprocessableEntityError, etc.
    # fall through here. We re-raise the original so genuinely unknown
    # cases surface as bugs rather than being miscategorised.
    raise exc


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
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APIError as exc:
            raise _translate_anthropic_error(exc) from exc
        return message.content[0].text

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        try:
            async with self._async_client.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.APIError as exc:
            raise _translate_anthropic_error(exc) from exc

    @property
    def model_name(self) -> str:
        return self._model
