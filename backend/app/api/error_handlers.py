"""Exception → HTTP response mapping.

Three handlers cover every failure mode:

* ``handle_domain_error`` — expected user-facing errors raised by services.
* ``handle_validation_error`` — FastAPI's request validation failures.
* ``handle_unexpected`` — anything else. Logs the traceback and returns a
  generic envelope; we never leak internal error text to callers.

All three emit the same envelope so the frontend has exactly one shape to
parse. See ``app/schemas/errors.py``.
"""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    AccountDisabled,
    DomainError,
    EmailAlreadyRegistered,
    FileTooLarge,
    Forbidden,
    GmailAuthError,
    InvalidCredentials,
    InvalidToken,
    LlmRateLimited,
    LlmTimeout,
    LlmUnavailable,
    NotFound,
    ServiceUnavailable,
    UnsupportedFileType,
)

logger = logging.getLogger(__name__)

_STATUS: dict[type[DomainError], int] = {
    InvalidCredentials: 401,
    InvalidToken: 401,
    AccountDisabled: 403,
    Forbidden: 403,
    NotFound: 404,
    EmailAlreadyRegistered: 409,
    FileTooLarge: 413,
    UnsupportedFileType: 415,
    LlmRateLimited: 429,
    ServiceUnavailable: 503,
    LlmUnavailable: 503,
    LlmTimeout: 504,
    GmailAuthError: 400,
}


def _envelope(
    code: str, message: str, details: object | None = None
) -> dict[str, object]:
    body: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return {"error": body}


async def handle_domain_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    status_code = _STATUS.get(type(exc), 400)
    # Fall back on a parent-class match if the exact type isn't in the
    # registry. Lets ``LlmProviderError`` subclasses not in ``_STATUS``
    # pick up the base-class status code for free.
    if type(exc) not in _STATUS:
        for ancestor in type(exc).__mro__[1:]:
            if ancestor in _STATUS:
                status_code = _STATUS[ancestor]
                break
    message = str(exc) or type(exc).__name__
    return JSONResponse(
        status_code=status_code,
        content=_envelope(exc.code, message, details=exc.details()),
    )


async def handle_http_exception(_request: Request, exc: Exception) -> JSONResponse:
    """Re-shape FastAPI's built-in ``HTTPException`` (e.g. missing auth header).

    Our own code should raise domain errors, but FastAPI's security utilities
    and a handful of framework internals still raise ``HTTPException`` directly.
    We wrap them so every non-2xx response uses the same envelope.
    """
    assert isinstance(exc, HTTPException)
    try:
        code = HTTPStatus(exc.status_code).phrase.lower().replace(" ", "_")
    except ValueError:
        code = "http_error"
    message = str(exc.detail) if exc.detail else code.replace("_", " ").capitalize()
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code, message),
        headers=exc.headers,
    )


async def handle_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        {
            "field": ".".join(str(p) for p in err["loc"]),
            "message": err["msg"],
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_envelope(
            "validation_error",
            "Request is invalid.",
            details,
        ),
    )


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=_envelope(
            "internal_error",
            "An unexpected error occurred. Please try again.",
        ),
    )
