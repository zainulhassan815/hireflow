"""Per-user Gmail resume sync.

One ``sync`` call = one poll of one user's Gmail for new messages with
resume-eligible attachments, each ingested via ``DocumentService`` and
deduped in ``gmail_ingested_messages``. A connection with a backfill
cursor set spends whatever budget the incremental pass leaves over on
walking backwards through older mail, one batch per run.

Invariants this service upholds:

* A single ``gmail_message_id`` is never ingested twice for the same
  connection (DB-level unique constraint + ``claim_or_skip``).
* A worker crash leaves at most a ``claimed`` row with no documents;
  the 15-minute visibility sweep rescues it on the next tick.
* Transient HTTP failures propagate to the Celery task for retry; the
  service never silently swallows them.
* Permanent OAuth failure (``invalid_grant``) auto-disconnects the
  connection and emits a ``GMAIL_DISCONNECT`` activity with the reason.
* A backfill cursor only ever moves backwards, so a crashed or
  half-finished pass re-walks ground that dedup then absorbs.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from uuid import UUID

from app.adapters.protocols import (
    GmailApi,
    GmailHistoryEvent,
    GmailMessage,
    GmailOAuth,
    HistoryExpired,
    InvalidGrant,
)
from app.domain.exceptions import NotFound
from app.models import (
    ActivityAction,
    GmailConnection,
    GmailIngestedMessage,
    User,
)
from app.repositories.gmail_connection import GmailConnectionRepository
from app.repositories.gmail_ingested_message import (
    GmailIngestedMessageRepository,
)
from app.repositories.user import UserRepository
from app.services.activity_service import ActivityService
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)

# Gmail sync is narrower than DocumentService's full MIME allowlist on
# purpose: email bodies are littered with signature logos and screenshots
# that F22's OCR would dutifully fail on and leave as 'failed'
# documents. Resumes sent by email are overwhelmingly PDF or Word.
# Someone sending a scanned-image resume can still upload manually.
_SYNC_ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }
)


class _PassResult(NamedTuple):
    """Outcome of draining one Gmail query."""

    listed: int
    work: int
    oldest: datetime | None


@dataclass
class SyncReport:
    scanned: int = 0
    ingested: int = 0
    skipped_dedup: int = 0
    skipped_no_eligible_attachment: int = 0
    errors: int = 0
    errors_by_type: Counter[str] = field(default_factory=Counter)
    needs_reauth: bool = False
    backfilled: int = 0
    backfill_cursor: datetime | None = None
    backfill_finished: bool = False
    source_trashed: int = 0
    source_purged: int = 0
    source_restored: int = 0
    documents_deleted: int = 0

    @property
    def work_done(self) -> int:
        """Messages that cost a Gmail fetch.

        Dedup skips are excluded: ``claim_or_skip`` short-circuits before
        ``get_message``, so re-seeing a known message costs one DB
        roundtrip and no Gmail quota. Budgeting on this rather than on
        raw scans is what lets a backfill page past already-ingested
        history instead of spending its whole allowance skipping it.
        """
        return self.scanned - self.skipped_dedup

    def summary(self) -> str:
        """Short single-line summary for activity log / beat output."""
        if self.needs_reauth:
            return "needs reconnecting: refresh token rejected"
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
        if (
            self.source_trashed
            or self.source_purged
            or self.source_restored
            or self.documents_deleted
        ):
            # Trashed and purged are reported apart on purpose: a trash is
            # reversible and never deletes, a purge is what actually can.
            # A single "source_deleted" counter made a trashed message look
            # like a mirroring failure when docs_deleted stayed 0.
            parts.append(f"source_trashed={self.source_trashed}")
            parts.append(f"source_purged={self.source_purged}")
            parts.append(f"source_restored={self.source_restored}")
            parts.append(f"docs_deleted={self.documents_deleted}")
        if self.backfilled or self.backfill_cursor or self.backfill_finished:
            parts.append(f"backfilled={self.backfilled}")
            if self.backfill_finished:
                parts.append("backfill=complete")
            elif self.backfill_cursor:
                parts.append(f"backfill_cursor={self.backfill_cursor:%Y-%m-%d}")
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
        max_pages_per_run: int,
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
        self._max_pages = max_pages_per_run

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
            await self._mark_needs_reauth(connection)
            return SyncReport(needs_reauth=True)

        report = SyncReport()

        # Change detection first, so a message deleted in Gmail is marked
        # before this run's drains touch anything. Isolated from the rest:
        # losing change detection must never cost us new resumes.
        try:
            await self._history_pass(
                connection=connection,
                owner=owner,
                access_token=tokens.access_token,
                report=report,
            )
        except Exception:
            logger.exception(
                "history pass failed for %s; continuing with ingestion",
                connection.gmail_email,
            )

        # New mail always outranks history: a connection working through
        # three years of backfill must not stop ingesting today's resumes.
        await self._drain(
            connection=connection,
            owner=owner,
            access_token=tokens.access_token,
            query=self._build_query(connection),
            budget=self._max_per_run,
            report=report,
        )

        if connection.backfill_before is not None:
            remaining = self._max_per_run - report.work_done
            if remaining > 0:
                await self._backfill_pass(
                    connection=connection,
                    owner=owner,
                    access_token=tokens.access_token,
                    budget=remaining,
                    report=report,
                )

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

    async def _history_pass(
        self,
        *,
        connection: GmailConnection,
        owner: User,
        access_token: str,
        report: SyncReport,
    ) -> None:
        """Replay Gmail's change feed since the stored cursor."""
        if connection.last_history_id is None:
            # Nothing to diff against on a first run. Seed and wait for
            # the next one — anything that changed before we had a cursor
            # is simply not knowable.
            profile = await self._api.get_profile(access_token)
            await self._connections.set_history_id(connection, profile.history_id)
            logger.info(
                "seeded history cursor for %s at %s",
                connection.gmail_email,
                profile.history_id,
            )
            return

        # Order is load-bearing: a message can be trashed and restored
        # inside one page, and only its final state is true. Replaying
        # into a dict keyed by message id keeps the last event per
        # message; folding into sets would lose that.
        latest: dict[str, GmailHistoryEvent] = {}
        newest_history_id = connection.last_history_id
        page_token: str | None = None

        try:
            for _ in range(self._max_pages):
                page = await self._api.list_history(
                    access_token,
                    start_history_id=connection.last_history_id,
                    page_token=page_token,
                )
                for message_id, event in page.events:
                    latest[message_id] = event
                if page.history_id:
                    newest_history_id = page.history_id
                if not page.next_page_token:
                    break
                page_token = page.next_page_token
        except HistoryExpired:
            # The changes inside the gap are unrecoverable — closing that
            # would mean listing every message and diffing the ledger,
            # which is the full scan the history API exists to avoid.
            logger.warning(
                "history cursor expired for %s; re-seeding", connection.gmail_email
            )
            await self._connections.set_history_id(connection, None)
            return

        for message_id, event in latest.items():
            await self._apply_history_event(
                connection=connection,
                owner=owner,
                message_id=message_id,
                event=event,
                report=report,
            )

        await self._connections.set_history_id(connection, newest_history_id)

    async def _apply_history_event(
        self,
        *,
        connection: GmailConnection,
        owner: User,
        message_id: str,
        event: GmailHistoryEvent,
        report: SyncReport,
    ) -> None:
        row = await self._ingested.get_by_message_id(connection.id, message_id)
        if row is None:
            # A message we never ingested. Most history traffic is this.
            return

        if event is GmailHistoryEvent.RESTORED:
            if row.source_deleted_at is not None:
                await self._ingested.set_source_deleted(row, None)
                report.source_restored += 1
            return

        await self._ingested.set_source_deleted(row, datetime.now(UTC))

        # Trashing is reversible, so it never destroys anything — not even
        # on an opted-in connection. Only a message Gmail reports as
        # permanently gone (Trash emptied, by the user or by Gmail's own
        # 30-day purge) can take documents with it.
        if event is GmailHistoryEvent.DELETED:
            report.source_purged += 1
            if connection.mirror_deletions:
                await self._mirror_deletion(
                    connection=connection, owner=owner, row=row, report=report
                )
            else:
                logger.info(
                    "message %s purged in Gmail; %s has mirror_deletions off, "
                    "keeping %d document(s)",
                    message_id,
                    connection.gmail_email,
                    len(row.document_ids),
                )
        else:
            report.source_trashed += 1
            logger.info(
                "message %s moved to Trash in Gmail; marking source as deleted. "
                "Documents are kept until the message is permanently deleted.",
                message_id,
            )

    async def _mirror_deletion(
        self,
        *,
        connection: GmailConnection,
        owner: User,
        row: GmailIngestedMessage,
        report: SyncReport,
    ) -> None:
        """Delete the documents a permanently-deleted message produced.

        Irreversible: drops the blob, the embeddings, and — via
        ``ON DELETE CASCADE`` on ``candidate_attachments`` — the file's
        link to any candidate. Every deletion is logged so an audit can
        answer why a document vanished.
        """
        for document_id in row.document_ids:
            try:
                await self._documents.delete(document_id, actor=owner)
            except NotFound:
                # Already removed by hand. Nothing to mirror.
                continue
            except Exception:
                logger.exception(
                    "failed to mirror deletion of document %s", document_id
                )
                continue

            report.documents_deleted += 1
            await self._activity.log(
                actor_id=connection.user_id,
                action=ActivityAction.DOCUMENT_DELETE,
                resource_type="document",
                resource_id=str(document_id),
                detail=(
                    f"mirrored Gmail deletion of message {row.gmail_message_id} "
                    f"on {connection.gmail_email}"
                ),
            )

    async def _drain(
        self,
        *,
        connection: GmailConnection,
        owner: User,
        access_token: str,
        query: str,
        budget: int,
        report: SyncReport,
    ) -> _PassResult:
        """Page through ``query`` until ``budget`` messages have been fetched.

        Dedup skips don't spend budget — only messages we actually claim
        and fetch do. ``_max_pages`` bounds the walk so a mailbox whose
        history is entirely ingested can't page forever looking for work
        that isn't there.
        """
        listed = 0
        work = 0
        oldest: datetime | None = None
        page_token: str | None = None

        for _ in range(self._max_pages):
            page = await self._api.list_messages(
                access_token, query=query, page_token=page_token
            )
            for summary in page.messages:
                listed += 1
                if work >= budget:
                    return _PassResult(listed, work, oldest)
                report.scanned += 1

                claim = await self._ingested.claim_or_skip(
                    connection.id, summary.message_id
                )
                if claim is None:
                    report.skipped_dedup += 1
                    continue

                work += 1
                internal_date = await self._handle_one(
                    connection=connection,
                    owner=owner,
                    access_token=access_token,
                    claim=claim,
                    message_id=summary.message_id,
                    report=report,
                )
                if internal_date is not None and (
                    oldest is None or internal_date < oldest
                ):
                    oldest = internal_date

            if not page.next_page_token:
                break
            page_token = page.next_page_token

        return _PassResult(listed, work, oldest)

    async def _backfill_pass(
        self,
        *,
        connection: GmailConnection,
        owner: User,
        access_token: str,
        budget: int,
        report: SyncReport,
    ) -> None:
        """Walk one batch further back in history and move the cursor."""
        cursor = connection.backfill_before
        floor = connection.backfill_until
        if cursor is None or floor is None:
            return

        # ``before:`` is exclusive and day-granular, so bound on the day
        # *after* the cursor — otherwise the cursor's own day drops out of
        # range the moment the cursor lands inside it, silently skipping
        # every message on that day we hadn't reached yet.
        query = f"has:attachment before:{cursor + timedelta(days=1):%Y/%m/%d}"
        result = await self._drain(
            connection=connection,
            owner=owner,
            access_token=access_token,
            query=query,
            budget=budget,
            report=report,
        )
        report.backfilled = result.work

        if result.listed == 0:
            await self._finish_backfill(connection, report)
            return

        if result.work and result.oldest is not None:
            new_cursor = result.oldest
        else:
            # Nothing new in this window — it's already fully ingested.
            # Step back a day so the walk can't stall re-skipping it.
            #
            # ponytail: a single day holding more than max_pages*100
            # attachment messages exhausts the budget on dedup skips,
            # yields a zero-work pass, and steps past the remainder.
            # Gmail accepts epoch-second before:/after: bounds — switch to
            # those if a mailbox ever hits that ceiling.
            new_cursor = cursor - timedelta(days=1)

        if new_cursor <= floor:
            await self._finish_backfill(connection, report)
            return

        await self._connections.advance_backfill(connection, new_cursor)
        report.backfill_cursor = new_cursor

    async def _finish_backfill(
        self, connection: GmailConnection, report: SyncReport
    ) -> None:
        await self._connections.finish_backfill(connection)
        report.backfill_cursor = None
        report.backfill_finished = True
        logger.info("backfill complete for %s", connection.gmail_email)

    async def _handle_one(
        self,
        *,
        connection: GmailConnection,
        owner: User,
        access_token: str,
        claim: GmailIngestedMessage,
        message_id: str,
        report: SyncReport,
    ) -> datetime | None:
        """Process a single claimed Gmail message. Never raises.

        Returns the message's own timestamp, which the backfill cursor
        walks backwards on. ``None`` when the message never got far
        enough to have one.
        """
        try:
            message = await self._api.get_message(access_token, message_id)
            internal_date = _internal_date(message)
            eligible = self._eligible_attachments(message)
            if not eligible:
                await self._ingested.mark_completed(
                    claim, attachment_count=0, document_ids=[]
                )
                report.skipped_no_eligible_attachment += 1
                return internal_date

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
            return internal_date
        except Exception as exc:
            type_name = type(exc).__name__
            logger.exception(
                "ingest failed: connection=%s message=%s",
                connection.id,
                message_id,
            )
            try:
                await self._ingested.mark_failed(claim, reason=f"{type_name}: {exc}")
            except Exception:
                # If marking the row fails (DB blip), don't propagate —
                # the stale-claim sweep will rescue it on the next run.
                logger.exception(
                    "could not record mark_failed for claim %s; "
                    "stale-claim sweep will recover it",
                    claim.id,
                )
            report.errors += 1
            report.errors_by_type[type_name] += 1
            return None

    def _eligible_attachments(self, message: GmailMessage) -> list:
        """Filter attachments by MIME and size before downloading bytes."""
        max_bytes = self._documents.max_size_bytes
        return [
            a
            for a in message.attachments
            if a.mime_type in _SYNC_ALLOWED_MIME_TYPES and 0 < a.size_bytes <= max_bytes
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

    async def _mark_needs_reauth(self, connection: GmailConnection) -> None:
        """Flag the connection for reconnection; do not delete it.

        Google expires refresh tokens after 7 days while the consent
        screen is in Testing, so this is a routine weekly event, not a
        rare failure. Deleting the row would cascade
        ``gmail_ingested_messages`` away and the next reconnect would
        re-import every message and duplicate every attachment. Keeping
        it means ``UNIQUE (user_id, gmail_email)`` lands the reconnect on
        this same row with its ledger, backfill cursor and mirroring
        setting intact.
        """
        await self._connections.mark_needs_reauth(connection)
        await self._activity.log(
            actor_id=connection.user_id,
            action=ActivityAction.GMAIL_REAUTH_REQUIRED,
            resource_type="gmail_connection",
            resource_id=str(connection.id),
            detail=f"{connection.gmail_email} needs reconnecting: refresh token rejected",
        )
        logger.warning(
            "%s needs reconnecting: refresh token rejected", connection.gmail_email
        )


def _internal_date(message: GmailMessage) -> datetime | None:
    """Gmail's ``internalDate`` as a datetime, or None when absent.

    The adapter defaults the field to 0 when Gmail omits it; treating that
    as 1970 would rocket a backfill cursor past its floor and end the walk.
    """
    if not message.internal_date_ms:
        return None
    return datetime.fromtimestamp(message.internal_date_ms / 1000, UTC)
