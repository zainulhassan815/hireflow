"""F81.i: adapter-level error translations.

We test the ``_translate_*`` helpers directly with real SDK exception
instances rather than mocking full ``async with client.stream(...)``
context managers. The behaviour we care about is the mapping, not the
plumbing — and the mapping is a pure function of the exception type.
"""

from __future__ import annotations

import json
import urllib.error
from typing import Any

import anthropic
import httpx
import pytest

from app.adapters.llm.claude import (
    _parse_retry_after,
    _translate_anthropic_error,
)
from app.adapters.llm.ollama import (
    _translate_httpx_error,
    _translate_urllib_error,
)
from app.domain.exceptions import (
    DomainError,
    InvalidCredentials,
    LlmProviderError,
    LlmRateLimited,
    LlmTimeout,
    LlmUnavailable,
)

# --------------------------------------------------------------------------
# DomainError.details() contract
# --------------------------------------------------------------------------


def test_domain_error_details_default_is_none() -> None:
    """Existing subclasses that don't override must keep emitting
    ``{code, message}`` with no details — backwards-compat with every
    4xx route that predates F81.i."""
    assert DomainError().details() is None
    assert InvalidCredentials("bad").details() is None


def test_llm_rate_limited_details_round_trip() -> None:
    with_retry = LlmRateLimited(retry_after_seconds=30)
    assert with_retry.details() == {"retry_after_seconds": 30}
    assert with_retry.code == "llm_rate_limited"

    without_retry = LlmRateLimited()
    assert without_retry.details() is None


# --------------------------------------------------------------------------
# Retry-After header parsing
# --------------------------------------------------------------------------


class _ResponseWithHeaders:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({}, None),
        ({"retry-after": "42"}, 42),
        ({"Retry-After": "7"}, 7),  # case-insensitive header lookup
        ({"retry-after": "not-a-number"}, None),  # graceful parse failure
        ({"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"}, None),  # HTTP-date form
    ],
)
def test_parse_retry_after(headers: dict[str, str], expected: int | None) -> None:
    assert _parse_retry_after(_ResponseWithHeaders(headers)) == expected


def test_parse_retry_after_handles_none_response() -> None:
    assert _parse_retry_after(None) is None


# --------------------------------------------------------------------------
# Anthropic error translation
# --------------------------------------------------------------------------


def _anthropic_response(
    *, status_code: int, headers: dict[str, str] | None = None
) -> httpx.Response:
    """Build an ``httpx.Response`` with a bound request so Anthropic's
    exception classes accept it. The SDK's ``APIStatusError``
    constructors need a real-ish response to inspect."""
    return httpx.Response(
        status_code=status_code,
        headers=headers or {},
        request=httpx.Request("POST", "https://api.anthropic.test/v1/messages"),
    )


def _raise_anthropic_status(
    exc_cls: type[anthropic.APIStatusError],
    *,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> anthropic.APIStatusError:
    """Construct an Anthropic status-error without calling the real API."""
    return exc_cls(
        message="test",
        response=_anthropic_response(status_code=status_code, headers=headers),
        body=None,
    )


def test_translate_rate_limit_with_retry_after() -> None:
    exc = _raise_anthropic_status(
        anthropic.RateLimitError,
        status_code=429,
        headers={"retry-after": "12"},
    )
    result = _translate_anthropic_error(exc)
    assert isinstance(result, LlmRateLimited)
    assert result.retry_after_seconds == 12


def test_translate_rate_limit_without_retry_after() -> None:
    exc = _raise_anthropic_status(anthropic.RateLimitError, status_code=429)
    result = _translate_anthropic_error(exc)
    assert isinstance(result, LlmRateLimited)
    assert result.retry_after_seconds is None


def test_translate_timeout() -> None:
    exc = anthropic.APITimeoutError(
        httpx.Request("POST", "https://api.anthropic.test/v1/messages"),
    )
    result = _translate_anthropic_error(exc)
    assert isinstance(result, LlmTimeout)


@pytest.mark.parametrize(
    "exc_cls",
    [
        anthropic.AuthenticationError,
        anthropic.PermissionDeniedError,
        anthropic.InternalServerError,
    ],
)
def test_translate_unavailable_variants(
    exc_cls: type[anthropic.APIStatusError],
) -> None:
    # Status codes chosen so each class's assertion passes; mapping
    # doesn't branch on status, only on type.
    status_map: dict[type[anthropic.APIStatusError], int] = {
        anthropic.AuthenticationError: 401,
        anthropic.PermissionDeniedError: 403,
        anthropic.InternalServerError: 500,
    }
    exc = _raise_anthropic_status(exc_cls, status_code=status_map[exc_cls])
    assert isinstance(_translate_anthropic_error(exc), LlmUnavailable)


def test_translate_connection_error() -> None:
    exc = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.test/v1/messages"),
    )
    assert isinstance(_translate_anthropic_error(exc), LlmUnavailable)


def test_translate_unknown_anthropic_error_re_raises() -> None:
    """BadRequestError (e.g. generic 400) isn't in our mapping — it
    should bubble up so RagService's last-resort ``except Exception``
    logs the traceback rather than being silently categorised."""
    exc = _raise_anthropic_status(anthropic.BadRequestError, status_code=400)
    with pytest.raises(anthropic.BadRequestError):
        _translate_anthropic_error(exc)


# --------------------------------------------------------------------------
# httpx error translation (Ollama async path)
# --------------------------------------------------------------------------


def test_translate_httpx_timeout() -> None:
    result = _translate_httpx_error(httpx.ReadTimeout("slow"))
    assert isinstance(result, LlmTimeout)


def test_translate_httpx_connect_error() -> None:
    result = _translate_httpx_error(httpx.ConnectError("refused"))
    assert isinstance(result, LlmUnavailable)


def test_translate_httpx_429_is_rate_limited() -> None:
    response = httpx.Response(
        status_code=429,
        request=httpx.Request("POST", "http://localhost:11434"),
    )
    exc = httpx.HTTPStatusError("rate", request=response.request, response=response)
    result = _translate_httpx_error(exc)
    assert isinstance(result, LlmRateLimited)


def test_translate_httpx_other_status_is_unavailable() -> None:
    response = httpx.Response(
        status_code=500,
        request=httpx.Request("POST", "http://localhost:11434"),
    )
    exc = httpx.HTTPStatusError("oops", request=response.request, response=response)
    result = _translate_httpx_error(exc)
    assert isinstance(result, LlmUnavailable)


def test_translate_httpx_json_decode_is_unavailable() -> None:
    exc = json.JSONDecodeError("bad", "", 0)
    result = _translate_httpx_error(exc)
    assert isinstance(result, LlmUnavailable)


# --------------------------------------------------------------------------
# urllib error translation (Ollama sync path, Celery workers)
# --------------------------------------------------------------------------


def test_translate_urllib_timeout() -> None:
    assert isinstance(_translate_urllib_error(TimeoutError("slow")), LlmTimeout)


def test_translate_urllib_429() -> None:
    exc = urllib.error.HTTPError(
        url="http://localhost:11434",
        code=429,
        msg="rate",
        hdrs=None,
        fp=None,  # type: ignore[arg-type]
    )
    assert isinstance(_translate_urllib_error(exc), LlmRateLimited)


def test_translate_urllib_connection_error() -> None:
    exc = urllib.error.URLError("refused")
    assert isinstance(_translate_urllib_error(exc), LlmUnavailable)


def test_translate_urllib_json_decode() -> None:
    exc = json.JSONDecodeError("bad", "", 0)
    assert isinstance(_translate_urllib_error(exc), LlmUnavailable)


# --------------------------------------------------------------------------
# Inheritance: LlmProviderError catches all three subclasses
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        LlmUnavailable("down"),
        LlmRateLimited(retry_after_seconds=5),
        LlmTimeout("slow"),
    ],
)
def test_all_subclasses_are_llm_provider_error(exc: Any) -> None:
    """RagService's ``except LlmProviderError`` branch depends on this."""
    assert isinstance(exc, LlmProviderError)
