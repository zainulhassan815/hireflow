"""Gmail REST API client.

Separate from the OAuth adapter (``gmail_oauth.py``) by design: this
class only reads Gmail data with an already-valid access token. Token
lifecycle — exchange / refresh / revoke — stays in the OAuth module so
each adapter has one reason to change.

Only the three methods we need today are implemented:

* ``list_messages`` — paginates ``users/me/messages`` with a query.
* ``get_message`` — fetches a single message in ``metadata`` format and
  flattens nested MIME parts into a list of attachment references.
* ``download_attachment`` — pulls attachment bytes (base64url decoded).

Attachment-less messages surface with ``attachments=[]``. Inline images
(Content-Disposition: inline) are not treated as attachments.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Iterable

import httpx

from app.adapters.protocols import (
    GmailAttachmentRef,
    GmailMessage,
    GmailMessagePage,
    GmailMessageSummary,
)

logger = logging.getLogger(__name__)

_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
_LIST_PAGE_SIZE = 100
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class GoogleGmailApi:
    """``GmailApi`` protocol implementation against Google's REST API."""

    async def list_messages(
        self, access_token: str, *, query: str, page_token: str | None = None
    ) -> GmailMessagePage:
        params: dict[str, str | int] = {
            "q": query,
            "maxResults": _LIST_PAGE_SIZE,
        }
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{_BASE}/messages",
                params=params,
                headers=_auth_header(access_token),
            )
        _raise_for_status(response, "list_messages")

        payload = response.json()
        messages = [
            GmailMessageSummary(message_id=m["id"], thread_id=m["threadId"])
            for m in payload.get("messages", [])
        ]
        return GmailMessagePage(
            messages=messages,
            next_page_token=payload.get("nextPageToken"),
        )

    async def get_message(self, access_token: str, message_id: str) -> GmailMessage:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{_BASE}/messages/{message_id}",
                params={"format": "full"},
                headers=_auth_header(access_token),
            )
        _raise_for_status(response, "get_message")

        payload = response.json()
        attachments = list(_walk_attachments(payload.get("payload", {})))
        return GmailMessage(
            message_id=payload["id"],
            thread_id=payload["threadId"],
            internal_date_ms=int(payload.get("internalDate", 0)),
            attachments=attachments,
        )

    async def download_attachment(
        self, access_token: str, message_id: str, attachment_id: str
    ) -> bytes:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{_BASE}/messages/{message_id}/attachments/{attachment_id}",
                headers=_auth_header(access_token),
            )
        _raise_for_status(response, "download_attachment")
        data_b64 = response.json().get("data", "")
        # Gmail API returns base64url-encoded bytes.
        return base64.urlsafe_b64decode(data_b64 + "=" * (-len(data_b64) % 4))


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _raise_for_status(response: httpx.Response, operation: str) -> None:
    if response.is_success:
        return
    # Log without the body — Gmail error payloads sometimes echo request
    # details; keep the log tidy and leak-free.
    logger.warning("gmail api %s returned %s", operation, response.status_code)
    response.raise_for_status()


def _walk_attachments(part: dict) -> Iterable[GmailAttachmentRef]:
    """Depth-first walk over a MIME tree, yielding real attachments only.

    A part is an attachment when:
      * it has a non-empty ``filename``,
      * its body has an ``attachmentId`` (i.e. the bytes are fetched
        separately, not inlined), and
      * it is not a multipart container.
    """
    mime_type = part.get("mimeType", "")
    filename = part.get("filename") or ""
    body = part.get("body") or {}
    attachment_id = body.get("attachmentId")

    if filename and attachment_id and not mime_type.startswith("multipart/"):
        yield GmailAttachmentRef(
            attachment_id=attachment_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=int(body.get("size", 0)),
        )

    for child in part.get("parts") or []:
        yield from _walk_attachments(child)
