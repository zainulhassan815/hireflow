"""Email delivery stub.

In production this will be swapped for a real provider (SES / SendGrid /
SMTP). For now every `send_*` call logs the message so developers can pick
the URL out of the server log during manual testing.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)


async def send_password_reset_email(to: str, reset_url: str) -> None:
    message = f"password reset email to={to} url={reset_url}"
    logger.info(message)
    # Stubbed transport: also write to stderr so devs can copy the URL out
    # during manual testing regardless of how uvicorn's logger is configured.
    print(f"[email-stub] {message}", file=sys.stderr, flush=True)
