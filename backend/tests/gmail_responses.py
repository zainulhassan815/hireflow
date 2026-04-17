"""Canned Gmail API response bodies for ``respx`` to serve.

Keep these realistic — minimum fields Google actually returns, same
shapes as the live API. One happy-path message with two eligible PDF
attachments, plus a third image attachment that sync should filter out.
"""

from __future__ import annotations

import base64

TOKEN_RESPONSE = {
    "access_token": "test-access-token",
    "expires_in": 3599,
    "scope": (
        "openid email "
        "https://www.googleapis.com/auth/gmail.readonly "
        "https://www.googleapis.com/auth/gmail.send"
    ),
    "token_type": "Bearer",
    # The token endpoint only returns refresh_token on the initial
    # exchange, not on refresh. Mirror that — tests that need a
    # refresh token response use EXCHANGE_RESPONSE below.
}

EXCHANGE_RESPONSE = {
    **TOKEN_RESPONSE,
    "refresh_token": "test-refresh-token",
}

USERINFO_RESPONSE = {
    "email": "candidate-source@example.com",
    "email_verified": True,
}

MESSAGE_ID = "abc123-message-id"

LIST_MESSAGES_RESPONSE = {
    "messages": [{"id": MESSAGE_ID, "threadId": "thread-1"}],
    "resultSizeEstimate": 1,
}

LIST_MESSAGES_EMPTY = {"resultSizeEstimate": 0}

ATTACHMENT_PDF_1 = "pdf-attachment-one"
ATTACHMENT_PDF_2 = "pdf-attachment-two"
ATTACHMENT_IMAGE = "signature-logo"

GET_MESSAGE_RESPONSE = {
    "id": MESSAGE_ID,
    "threadId": "thread-1",
    "internalDate": "1723000000000",
    "payload": {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "text/plain",
                "filename": "",
                "body": {"data": "aGVsbG8="},
            },
            {
                "mimeType": "application/pdf",
                "filename": "resume.pdf",
                "body": {"attachmentId": ATTACHMENT_PDF_1, "size": 12345},
            },
            {
                "mimeType": "application/pdf",
                "filename": "cover-letter.pdf",
                "body": {"attachmentId": ATTACHMENT_PDF_2, "size": 6789},
            },
            {
                "mimeType": "image/png",
                "filename": "signature.png",
                "body": {"attachmentId": ATTACHMENT_IMAGE, "size": 2048},
            },
        ],
    },
}


def attachment_response(payload_bytes: bytes) -> dict[str, str]:
    """Gmail wraps attachment bytes in base64url + a ``data`` key."""
    data = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    return {"data": data, "size": len(payload_bytes)}
