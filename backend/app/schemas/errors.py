"""Error response envelope.

Every 4xx/5xx response from the API shares this shape. The frontend's
``extractApiError`` helper is the one consumer; the generated SDK surfaces
``ErrorResponse`` so TypeScript can narrow on it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ValidationErrorDetail(BaseModel):
    """A single field-level validation failure."""

    field: str = Field(
        ...,
        description="Dotted path to the offending field (e.g. 'body.email').",
        examples=["body.email"],
    )
    message: str = Field(
        ...,
        description="Why this field failed validation.",
        examples=["value is not a valid email address"],
    )


class ErrorBody(BaseModel):
    """The payload under the top-level ``error`` key."""

    code: str = Field(
        ...,
        description=(
            "Stable machine-readable error code. Clients should switch on this "
            "to decide UX (e.g. redirect to login on 'invalid_token'). See the "
            "DomainError subclasses in the backend for the full set."
        ),
        examples=["invalid_credentials"],
    )
    message: str = Field(
        ...,
        description="Human-readable message safe to display to end users.",
        examples=["Invalid email or password."],
    )
    details: list[ValidationErrorDetail] | dict[str, Any] | None = Field(
        None,
        description=(
            "Optional structured context. Only populated for 'validation_error' "
            "(array of field failures) today; reserved for future per-code use."
        ),
    )


class ErrorResponse(BaseModel):
    """Top-level error envelope returned for every non-2xx response."""

    error: ErrorBody
