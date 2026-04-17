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
from typing import ClassVar

_CAMEL_TO_SNAKE = re.compile(r"(?<!^)(?=[A-Z])")


class DomainError(Exception):
    """Base class for all expected, user-facing domain errors."""

    code: ClassVar[str] = "bad_request"

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "code" not in cls.__dict__:
            cls.code = _CAMEL_TO_SNAKE.sub("_", cls.__name__).lower()


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
