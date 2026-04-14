"""Maps `DomainError` subclasses to HTTP responses.

Services raise domain errors; this module is the only place that knows
which error corresponds to which status code. Adding a new domain error
means extending `_STATUS` — nothing else changes.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    AccountDisabled,
    DomainError,
    EmailAlreadyRegistered,
    FileTooLarge,
    Forbidden,
    InvalidCredentials,
    InvalidToken,
    NotFound,
    UnsupportedFileType,
)

_STATUS: dict[type[DomainError], int] = {
    InvalidCredentials: 401,
    InvalidToken: 401,
    AccountDisabled: 403,
    Forbidden: 403,
    NotFound: 404,
    EmailAlreadyRegistered: 409,
    FileTooLarge: 413,
    UnsupportedFileType: 415,
}


async def handle_domain_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)  # registered for DomainError only
    status_code = _STATUS.get(type(exc), 400)
    return JSONResponse(
        status_code=status_code,
        content={"detail": str(exc) or type(exc).__name__},
    )
