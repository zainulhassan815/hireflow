"""Domain exceptions.

Services raise these; the api.error_handlers module maps them to HTTP
responses. Keeping service code HTTP-agnostic means the same services work
from FastAPI, a CLI, a background worker, or a test.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all expected, user-facing domain errors."""


class InvalidCredentials(DomainError):
    """Supplied email/password pair doesn't match any active account."""


class AccountDisabled(DomainError):
    """Account exists but has been deactivated."""


class EmailAlreadyRegistered(DomainError):
    """An account with this email already exists."""


class InvalidToken(DomainError):
    """Presented token is unrecognised, expired, revoked, or of the wrong type."""


class Forbidden(DomainError):
    """Caller is authenticated but not permitted to perform this action."""
