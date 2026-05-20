# 11 · Gmail sync

OAuth connect, scheduled poll, attachment ingestion into the document
pipeline. The only entry point into the corpus that isn't a user
upload.

---

## Purpose

Let HR users connect one or more Gmail mailboxes and have incoming
resumes ingested automatically. The sync must be:

- **Idempotent per `(connection, message_id)`** — retries never
  double-ingest.
- **Crash-safe** — a dead worker leaves at most a claimed row with
  no documents, which the stale-claim sweep rescues.
- **Self-healing on permanent auth failure** — `invalid_grant`
  auto-disconnects rather than retry-storming.
- **Narrowly scoped** — PDF / DOCX / DOC only; email signature
  images don't flood as "failed" docs.

---

## Flow

### Connect (run once per mailbox)

```
POST /api/auth/gmail/authorize
    │
    ▼
GmailService.begin_authorization  (gmail_service.py:58)
    state = random; stored in Redis (10-min TTL)
    delegates to GmailOAuth.build_authorize_url(state)
    returns Google consent URL

browser → Google consent → callback

GET /api/auth/gmail/callback?code=...&state=...
    │
    ▼
GmailService.complete_authorization  (gmail_service.py:65)
    pop + validate state from Redis
    exchange_code → OAuthTokens
    fetch_email
    GmailConnectionRepository.upsert(user_id, gmail_email,
                                     refresh_token encrypted, scopes)
    log ActivityAction.GMAIL_CONNECT
```

Refresh tokens stored encrypted (F73). `build_authorize_url` lives on
the **OAuth adapter** (`gmail_oauth.py:50`), not the service — the
service only owns the state lifecycle.

**Multi-account (F53.a).** A user can hold *multiple* connections.
The `gmail_connections` row is keyed `(user_id, gmail_email)`, and
`upsert` (`gmail_connection.py:67-90`) keys on both columns: re-
authorizing the *same* address updates that row's tokens + scopes in
place, while connecting a *different* Google account inserts a new
row. Connecting is not 1:1 and does not replace — each mailbox is an
independent connection with its own sync state.

### Scheduled sync (periodic)

```
celery beat       sync_all_gmail_connections (every N minutes)
    │
    ▼
worker/tasks.py::sync_all_gmail_connections
    │  list all connection_ids
    │  for each: sync_gmail_connection.delay(connection_id)
    ▼
worker/tasks.py::sync_gmail_connection
    │  asyncio.run(_run_sync(connection_id))
    │  on transient httpx error → self.retry (backoff, max 3 × 600s)
    │  on anything else → log + give up
    ▼
GmailSyncService.sync (services/gmail_sync_service.py:113)
    │
    │  1. fetch GmailConnection + owner User
    │  2. reset_stale_claims (any claim older than 15min → unclaimed)
    │  3. refresh OAuth tokens
    │       InvalidGrant → _auto_disconnect → SyncReport(disconnected=True)
    │  4. build query: "has:attachment newer_than:{N}d"
    │       N = initial_window_days on first sync, min(elapsed+1, initial) after
    │  5. while scanned < max_per_run:
    │       page = api.list_messages(...)
    │       for each message_id:
    │         _handle_one(connection, owner, access_token, message_id, report)
    │       if no next_page: break
    │  6. touch_sync (update last_synced_at)
    │  7. log ActivityAction.GMAIL_SYNC_RUN with summary
    ▼
SyncReport { scanned, ingested, skipped_dedup,
             skipped_no_eligible_attachment,
             errors, errors_by_type, disconnected }
```

### `_handle_one` — per-message

```
claim = ingested.claim_or_skip(connection_id, message_id)
    │
    │  uses DB unique constraint on (connection_id, gmail_message_id)
    │  to atomically claim OR skip if another worker got there first
    │
    │  claim == None → already ingested / claimed elsewhere → skip
    │
    ▼
try:
    message = api.get_message(message_id)
    eligible = filter attachments by MIME + size
        mime ∈ {pdf, docx, doc}
        size > 0 AND size ≤ MAX_FILE_SIZE_MB
    if no eligible:
        mark_completed(claim, 0, [])
        report.skipped_no_eligible_attachment += 1
        return

    for each ref in eligible:
        data = api.download_attachment(...)
        doc = DocumentService.upload(
            owner=owner, filename=ref.filename,
            mime_type=ref.mime_type, data=data,
        )
        extract_document_text.delay(str(doc.id))   # kick off pipeline
        document_ids.append(doc.id)

    mark_completed(claim, len(eligible), document_ids)
    report.ingested += 1
except Exception as exc:
    mark_failed(claim, reason=f"{type(exc).__name__}: {exc}")
    report.errors += 1
    report.errors_by_type[type(exc).__name__] += 1
```

The inner `extract_document_text.delay(...)` hands off to the
regular document processing pipeline (`01-document-upload-and-processing.md`).

---

## Key invariants

- **Unique constraint on `(connection_id, gmail_message_id)`** in
  `gmail_ingested_messages`. `claim_or_skip` uses `INSERT ... ON
  CONFLICT DO NOTHING RETURNING` (or equivalent) — two workers
  hitting the same message can't both claim it.
- **Claim → mark_completed OR mark_failed.** Every claim ends in one
  of the two. A worker crash between claim and mark leaves the row
  `claimed` + stale; `reset_stale_claims` on the next run
  unclaims it.
- **Transient errors retry, permanent errors don't.**
  `sync_gmail_connection` catches `httpx.TransportError` +
  `TimeoutException` → Celery retry; everything else logs and
  gives up (exhausting 3 retries costs us nothing except a log
  line).
- **OAuth `invalid_grant` ⇒ auto-disconnect.** User revoked at
  `myaccount.google.com` → we delete the connection, fire an
  activity log, stop polling. No retry storm.
- **Sync is narrower than manual upload.** PDF / DOCX / DOC only;
  images aren't auto-ingested because resume emails rarely
  attach one and email signatures would flood "failed" status.
- **`max_messages_per_run`** caps per-tick work so a user with a
  massive backlog doesn't monopolize the worker.
- **Look-back window grows adaptively.** First sync uses
  `initial_window_days`; subsequent syncs look back
  `max(1, elapsed_days + 1)` clamped to `initial_window_days`.
  1-day floor handles clock skew.

---

## Configuration knobs

| Setting | Default | Effect |
|---|---|---|
| `gmail_client_id` / `_secret` / `_redirect_uri` | none | OAuth app credentials. All must be set for Gmail to work. |
| `gmail_sync_interval_minutes` | 5 | Beat fan-out interval (`config.py:119`; consumed at `celery_app.py:37`). |
| `gmail_sync_max_messages_per_run` | 100 | Messages scanned per tick per connection. |
| `gmail_sync_initial_window_days` | 7 | Look-back on first sync. |
| `gmail_sync_claim_timeout_minutes` | 15 | Stale claim threshold. |

---

## Known issues / pain points

1. **No per-connection scheduling.** Every tick enumerates every
   connection; a quiet user still gets polled. A last-activity-based
   dynamic schedule would reduce API quota.
2. **Fan-out doesn't respect worker capacity.** 500 users → 500
   enqueued per-user tasks in one tick. Celery queues them fine;
   Gmail API quota per connection is the actual limit. Today we
   don't track aggregate quota.
3. **Stale-claim sweep only runs on the user's next sync.** A user
   whose connection is disabled entirely leaves stuck claims
   indefinitely. Cosmetic — those rows never surface to the user —
   but they accumulate.
4. **No push / Pub/Sub subscription.** Polling model has inherent
   latency (up to the beat interval) and API cost. Gmail offers
   `users.watch` Pub/Sub for push; scoped out as a follow-up.
5. **Dedup relies on `(connection_id, message_id)`** — if the same
   resume is emailed to two users, both ingest it independently.
   Intentional (each HR owns their corpus) but worth noting.
6. **Re-download cost on retry.** If `_handle_one` fails after
   downloading 2 of 3 attachments, Celery retries the whole message
   from scratch — the 2 downloaded attachments re-download. Small;
   worth accepting for code simplicity.
7. **Error type counter is Counter-of-class-names.** No breakdown
   by per-attachment vs per-message error. Limits what the activity
   log summary can convey.
8. **Attachment size-check happens after MIME filter, before
   download.** Good. But the size-check uses the listed
   `size_bytes` from Gmail, not the actual downloaded size — a
   Gmail bug (or MIME spoofing) could slip past.
9. **`GmailConnection` stores `gmail_email` redundantly with the
   user's email**. Fine today (the Google account can differ from
   the Hireflow login email) but occasionally confusing.
10. **Scope is fixed** — `gmail.readonly` (plus the OAuth
    basics). Can't let users pick a label filter like "resumes" to
    narrow ingestion. Nice-to-have.
11. **No delete on message side.** A resume ingested into Hireflow
    stays after the user deletes the original email. This is
    probably the right default (audit) but should be documented in
    a privacy note.

---

## Improvement opportunities

### Short-term

- **Stale-claim sweep scheduled task.** A daily fan-out job calls
  `reset_stale_claims` per connection even if the connection
  isn't being polled. Keeps the ingested-messages table clean.
- **Per-sync structured log line.** `scanned=X ingested=Y dedup=Z
  errors=E` with timing, per user. Piped to the dashboard for ops.
- **Activity-log entries per ingested doc.** Today we log the sync
  run summary; adding one `GMAIL_INGESTED` entry per doc gives the
  user a clear source attribution on the doc.

### Medium-term

- **Dynamic per-connection interval.** Track time-since-last-
  resume-ingested; back off quiet connections to once an hour,
  keep busy ones at 5 min. Cuts API calls materially.
- **Label filter.** Let users pick a Gmail label ("Applicants");
  only messages with that label ingest. Respects user's own filing.
- **Follow-up email send (F52).** Complements ingest — once we have
  a candidate row, let HR reply via Gmail API from the candidate
  detail page. Logged in activity trail.
- **Backpressure-aware fan-out.** Don't enqueue a user's sync if
  they already have one in flight. Trivial: Redis SETNX key by
  connection_id.

### Long-term

- **Push via Gmail Pub/Sub `users.watch`.** Removes polling latency
  + cost entirely. Needs a Pub/Sub topic + IAM dance; worth it at
  scale.
- **Cross-channel ingest Protocol.** Extract the `{fetch, dedupe,
  enqueue}` pattern into a `MailboxSync` Protocol and implement
  IMAP / Outlook / Microsoft Graph against it. Would let Outlook
  users connect without a rewrite.
- **Smart attachment detection.** Classify attachments before
  download (by filename heuristics) to pre-filter marketing
  images / invoices / forwarded threads. Gets expensive if wrong;
  keep conservative.

---

## Cross-references

- **Code**: `backend/app/services/gmail_sync_service.py`,
  `app/services/gmail_service.py`,
  `app/adapters/gmail_oauth.py`,
  `app/adapters/gmail_api.py`,
  `app/worker/tasks.py` (`sync_all_gmail_connections`,
  `sync_gmail_connection`),
  `app/repositories/gmail_connection.py`,
  `app/repositories/gmail_ingested_message.py`.
- **Handoff**: `01-document-upload-and-processing.md`.
- **Design**: `docs/features.md` F50, F51, F52 (deferred),
  `docs/architecture.md` §6 auth, §12 config.

---

## What changed

- **F53.a — multi-account + manual sync.** A user can now hold
  multiple Gmail connections, keyed `(user_id, gmail_email)`. The
  `/connections` sub-resource models it: `GET /api/auth/gmail/connections`
  lists, `POST /api/auth/gmail/connections/{connection_id}/sync`
  (`gmail.py:131-163`) triggers an immediate sync — returns `202` and
  enqueues `sync_gmail_connection.delay` — and
  `DELETE /api/auth/gmail/connections/{connection_id}` disconnects one
  mailbox without touching the others. The manual-resync endpoint
  retired the "no resync button" pain point.
