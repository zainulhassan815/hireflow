"""Domain exceptions.

Services raise these; `app.api.error_handlers` maps them to HTTP
responses. Keeping service code HTTP-agnostic means the same services work
from FastAPI, a CLI, a background worker, or a test.

Every subclass gets a stable machine-readable `code` derived from its name
(``InvalidCredentials`` → ``invalid_credentials``). The code is what the
frontend switches on; messages are human-readable and may change.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

_CAMEL_TO_SNAKE = re.compile(r"(?<!^)(?=[A-Z])")


class DomainError(Exception):
    """Base class for all expected, user-facing domain errors."""

    code: ClassVar[str] = "bad_request"

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "code" not in cls.__dict__:
            cls.code = _CAMEL_TO_SNAKE.sub("_", cls.__name__).lower()

    def details(self) -> dict[str, Any] | None:
        """Structured context for the error envelope. None = no details.

        Subclasses override to expose machine-readable fields (e.g.
        ``retry_after_seconds``). The default returns None so the full
        existing hierarchy stays backwards-compatible — callers that
        only care about ``{code, message}`` keep working unchanged.
        """
        return None


class InvalidCredentials(DomainError):
    """Supplied email/password pair doesn't match any active account."""


class AccountDisabled(DomainError):
    """Account exists but has been deactivated."""


class EmailAlreadyRegistered(DomainError):
    """An account with this email already exists."""


class InvalidToken(DomainError):
    """Presented token is unrecognised, expired, revoked, or of the wrong type."""


class NotFound(DomainError):
    """Requested resource does not exist."""


class FileTooLarge(DomainError):
    """Uploaded file exceeds the configured size limit."""


class UnsupportedFileType(DomainError):
    """The file's MIME type is not in the allowed set."""


class Forbidden(DomainError):
    """Caller is authenticated but not permitted to perform this action."""


class ServiceUnavailable(DomainError):
    """A required downstream provider (LLM, vision, storage) is not configured or reachable."""


class GmailAuthError(DomainError):
    """OAuth flow with Google failed (bad state, denied consent, exchange error)."""


# ---------- LLM provider errors (F81.i) ----------
#
# Adapters (ClaudeLlmProvider, OllamaLlmProvider) translate provider-
# specific exceptions (``anthropic.*``, ``httpx.*``) into these so the
# service layer never leaks SDK types. ``LlmProviderError`` is the
# catch-all for RagService's ``except`` block.


class LlmProviderError(DomainError):
    """Base for LLM-provider failures. Not raised directly — catch this
    in service code to handle every provider-origin error uniformly."""


class LlmUnavailable(LlmProviderError):
    """Provider is unreachable — network error, authentication failure,
    or a 5xx response from the provider."""


class LlmRateLimited(LlmProviderError):
    """Provider returned 429 Too Many Requests.

    Carries ``retry_after_seconds`` when the response's ``Retry-After``
    header was parseable as an integer (per RFC 7231 §7.1.3). The
    header may also be an HTTP-date; that form is not parsed — we fail
    loudly via ``None`` rather than shipping speculative date handling.
    """

    def __init__(
        self,
        message: str = "AI provider is rate-limited. Please try again shortly.",
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds

    def details(self) -> dict[str, Any] | None:
        if self.retry_after_seconds is None:
            return None
        return {"retry_after_seconds": self.retry_after_seconds}


class LlmTimeout(LlmProviderError):
    """Request to the provider timed out — connection was alive but the
    response didn't arrive inside the configured deadline."""
