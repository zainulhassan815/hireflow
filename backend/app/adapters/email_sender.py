"""Email delivery adapters.

The stub implementation logs and prints — enough for local development and
tests. Swap in a real transport (SES/SendGrid/SMTP) by implementing the
`EmailSender` protocol; no call site changes.
"""

from __future__ import annotations

import logging
import sys


class LoggingEmailSender:
    """Dev/test `EmailSender`: logs each outbound message and echoes to stderr.

    Stderr echo is intentional — uvicorn's default log config doesn't wire
    app loggers, so without it devs can't pick the password-reset URL out
    of the server output during manual testing.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    async def send_password_reset(self, to: str, reset_url: str) -> None:
        message = f"password reset email to={to} url={reset_url}"
        self._logger.info(message)
        print(f"[email-stub] {message}", file=sys.stderr, flush=True)
