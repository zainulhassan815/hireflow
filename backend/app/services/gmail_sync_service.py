"""Per-user Gmail resume sync.

One ``sync`` call = one poll of one user's Gmail for new messages with
resume-eligible attachments, each ingested via ``DocumentService`` and
deduped in ``gmail_ingested_messages``.

Invariants this service upholds:

* A single ``gmail_message_id`` is never ingested twice for the same
  connection (DB-level unique constraint + ``claim_or_skip``).
* A worker crash leaves at most a ``claimed`` row with no documents;
  the 15-minute visibility sweep rescues it on the next tick.
* Transient HTTP failures propagate to the Celery task for retry; the
  service never silently swallows them.
* Permanent OAuth failure (``invalid_grant``) auto-disconnects the
  connection and emits a ``GMAIL_DISCONNECT`` activity with the reason.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.adapters.protocols import (
    GmailApi,
    GmailMessage,
    GmailOAuth,
    InvalidGrant,
)
from app.models import ActivityAction, GmailConnection, User
from app.repositories.gmail_connection import GmailConnectionRepository
from app.repositories.gmail_ingested_message import (
    GmailIngestedMessageRepository,
)
from app.repositories.user import UserRepository
from app.services.activity_service import ActivityService
from app.services.document_service import ALLOWED_MIME_TYPES, DocumentService

logger = logging.getLogger(__name__)


@dataclass
class SyncReport:
    scanned: int = 0
    ingested: int = 0
    skipped_dedup: int = 0
    skipped_no_eligible_attachment: int = 0
    errors: int = 0
    errors_by_type: Counter[str] = field(default_factory=Counter)
    disconnected: bool = False

    def summary(self) -> str:
        """Short single-line summary for activity log / beat output."""
        if self.disconnected:
            return "auto-disconnected: token revoked"
        parts = [
            f"scanned={self.scanned}",
            f"ingested={self.ingested}",
            f"dedup={self.skipped_dedup}",
            f"no_attachment={self.skipped_no_eligible_attachment}",
            f"errors={self.errors}",
        ]
        if self.errors_by_type:
            top = ",".join(
                f"{name}:{count}" for name, count in self.errors_by_type.most_common(3)
            )
            parts.append(f"error_types={top}")
        return " ".join(parts)


class GmailSyncService:
    def __init__(
        self,
        *,
        oauth: GmailOAuth,
        api: GmailApi,
        connections: GmailConnectionRepository,
        ingested: GmailIngestedMessageRepository,
        users: UserRepository,
        documents: DocumentService,
        activity: ActivityService,
        max_messages_per_run: int,
        initial_window_days: int,
        claim_timeout_minutes: int,
    ) -> None:
        self._oauth = oauth
        self._api = api
        self._connections = connections
        self._ingested = ingested
        self._users = users
        self._documents = documents
        self._activity = activity
        self._max_per_run = max_messages_per_run
        self._initial_window_days = initial_window_days
        self._claim_timeout_minutes = claim_timeout_minutes

    async def sync(self, connection_id: UUID) -> SyncReport:
        connection = await self._connections.get_by_id(connection_id)
        if connection is None:
            logger.info("connection %s no longer exists; skipping", connection_id)
            return SyncReport()

        owner = await self._users.get(connection.user_id)
        if owner is None:
            logger.warning(
                "connection %s owner %s missing; skipping",
                connection.id,
                connection.user_id,
            )
            return SyncReport()

        # Reset any stuck claims before trying to acquire new ones.
        reset_count = await self._ingested.reset_stale_claims(
            connection.id, timeout_minutes=self._claim_timeout_minutes
        )
        if reset_count:
            logger.info(
                "reset %d stuck claims for connection %s", reset_count, connection.id
            )

        # Refresh tokens. Permanent failure ⇒ auto-disconnect.
        try:
            tokens = await self._oauth.refresh(connection.refresh_token)
        except InvalidGrant:
            await self._auto_disconnect(connection)
            return SyncReport(disconnected=True)

        query = self._build_query(connection)
        report = SyncReport()

        page_token: str | None = None
        while report.scanned < self._max_per_run:
            page = await self._api.list_messages(
                tokens.access_token, query=query, page_token=page_token
            )
            for summary in page.messages:
                if report.scanned >= self._max_per_run:
                    break
                report.scanned += 1
                await self._handle_one(
                    connection=connection,
                    owner=owner,
                    access_token=tokens.access_token,
                    message_id=summary.message_id,
                    report=report,
                )
            if not page.next_page_token:
                break
            page_token = page.next_page_token

        await self._connections.touch_sync(connection)

        await self._activity.log(
            actor_id=connection.user_id,
            action=ActivityAction.GMAIL_SYNC_RUN,
            resource_type="gmail_connection",
            resource_id=str(connection.id),
            detail=report.summary(),
        )
        logger.info(
            "gmail sync complete for %s: %s", connection.gmail_email, report.summary()
        )
        return report

    async def _handle_one(
        self,
        *,
        connection: GmailConnection,
        owner: User,
        access_token: str,
        message_id: str,
        report: SyncReport,
    ) -> None:
        """Process a single Gmail message end-to-end. Never raises."""
        claim = await self._ingested.claim_or_skip(connection.id, message_id)
        if claim is None:
            report.skipped_dedup += 1
            return

        try:
            message = await self._api.get_message(access_token, message_id)
            eligible = self._eligible_attachments(message)
            if not eligible:
                await self._ingested.mark_completed(
                    claim, attachment_count=0, document_ids=[]
                )
                report.skipped_no_eligible_attachment += 1
                return

            # Imported inside the function to avoid a circular import at
            # module load (worker.tasks imports services eagerly).
            from app.worker.tasks import extract_document_text

            document_ids: list[UUID] = []
            for ref in eligible:
                data = await self._api.download_attachment(
                    access_token, message_id, ref.attachment_id
                )
                doc = await self._documents.upload(
                    owner=owner,
                    filename=ref.filename,
                    mime_type=ref.mime_type,
                    data=data,
                )
                extract_document_text.delay(str(doc.id))
                document_ids.append(doc.id)

            await self._ingested.mark_completed(
                claim,
                attachment_count=len(eligible),
                document_ids=document_ids,
            )
            report.ingested += 1
        except Exception as exc:
            type_name = type(exc).__name__
            logger.exception(
                "ingest failed: connection=%s message=%s",
                connection.id,
                message_id,
            )
            await self._ingested.mark_failed(claim, reason=f"{type_name}: {exc}")
            report.errors += 1
            report.errors_by_type[type_name] += 1

    def _eligible_attachments(self, message: GmailMessage) -> list:
        """Filter attachments by MIME and size before downloading bytes."""
        max_bytes = self._documents.max_size_bytes
        return [
            a
            for a in message.attachments
            if a.mime_type in ALLOWED_MIME_TYPES and 0 < a.size_bytes <= max_bytes
        ]

    def _build_query(self, connection: GmailConnection) -> str:
        """Gmail search query bounded to the appropriate window."""
        if connection.last_synced_at is None:
            window_days = self._initial_window_days
        else:
            elapsed = datetime.now(UTC) - connection.last_synced_at
            # Always look back at least 1 day to catch clock skew /
            # messages that arrived right at the boundary.
            window_days = max(1, int(elapsed / timedelta(days=1)) + 1)
            window_days = min(window_days, self._initial_window_days)
        return f"has:attachment newer_than:{window_days}d"

    async def _auto_disconnect(self, connection: GmailConnection) -> None:
        gmail_email = connection.gmail_email
        connection_id = connection.id
        user_id = connection.user_id
        await self._connections.delete(connection)
        await self._activity.log(
            actor_id=user_id,
            action=ActivityAction.GMAIL_DISCONNECT,
            resource_type="gmail_connection",
            resource_id=str(connection_id),
            detail=f"{gmail_email} auto-disconnected: token revoked",
        )
        logger.warning("auto-disconnected %s: refresh token revoked", gmail_email)
