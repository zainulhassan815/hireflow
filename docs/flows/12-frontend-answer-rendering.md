# 12 · Frontend answer rendering

How the chat UI consumes the SSE stream, composes markdown answers,
turns `[filename.pdf]` markers into clickable chips, and renders
confidence + sources.

---

## Purpose

Make the RAG answer feel live, structured, and trustworthy:

- Tokens appear as they arrive (streaming UX).
- Markdown renders correctly — tables, lists, strikethrough — with
  citations surviving inside cells and list items.
- Inline `[alice_resume.pdf]` markers render as clickable chips that
  scroll to the source card.
- Confidence + intent badges set expectations before the user reads
  the answer.

---

## Flow

```
user hits Send in `pages/qa.tsx` (`QaPage`)
    │
    ▼
streamRagAnswer(request, handlers)  (api/rag-stream.ts:69)
    │
    │  fetch('/api/rag/stream', {
    │    method: POST,
    │    credentials: 'include',
    │    headers: { Authorization: Bearer <token>,
    │               Accept: 'text/event-stream' },
    │    body: JSON.stringify({ question, document_ids?, max_chunks? })
    │  })
    │
    │  response.body
    │   .pipeThrough(new TextDecoderStream())
    │   .getReader()
    │
    │  buffer bytes → split on \n\n → parseFrame per frame
    │    data: <json payload> → JSON.parse → RagStreamEvent
    │    (event: header ignored — discriminator is inside JSON)
    │
    ▼
handlers.onEvent(event)
    │
    ├── citations: set message.sources
    ├── delta:     append to message.content (triggers re-render)
    ├── done:      set model, timing, confidence, intent
    └── error:     mark message as errored, show toast
```

Final resolve on:
- `done` received → success.
- `error` received → terminal failure.
- Stream closes with neither → handled as abort / transport error.

Rejects only on **pre-stream** failures (401, 503 on open). Mid-
stream provider failures are delivered as `error` events.

---

## Message rendering

Each assistant message flows through:

```
ChatMessage { id, role, content, sources?, confidence?, intent? }
    │
    ▼
<AssistantMessage>
    │
    ├── empty + streaming → <ThinkingDots> (three pulsing dots)
    │   while streamingMessageId === id and content is empty
    │
    ├── once content arrives, a blinking BAR cursor
    │   (`h-4 w-1.5 ... animate-pulse`) trails the streamed text
    │
    ├── AssistantMarkdown
    │     ReactMarkdown
    │       remarkPlugins: [remarkGfm]
    │       components: overrides on p, li, td, th, table, ul, ol
    │         each override calls renderWithCitations(children, citations)
    │
    │   renderWithCitations walks only top-level string children;
    │   runs parseSegments per string; replaces matching [bracket]
    │   spans with <CitationMarker>.
    │
    ├── confidence Badge (green/amber/grey) when message.confidence set
    │
    ├── model + query_time_ms metadata line
    │
    └── <SourcesPanel>
          one card per citation
            filename · section_heading · p.N
            500-char snippet with <HighlightedText> match_spans
            id = qa-source-{messageId}-{index}   ← scroll target
```

### `parseSegments` — citation extraction

```typescript
const regex = /\[([^[\]\n]+)\]/g;
for each match:
  inner = match[1]
  citation = byFilename.get(inner)
          ?? byLower.get(inner.toLowerCase())
  if citation: replace the [...] span with a citation segment
  else: leave as text
```

- **Exact-filename match first**, lowercase fallback. Avoids
  false-positive chips on things like `[TODO]` or `[note]`.
- **Streaming-safe.** The regex only matches a *complete* `[...]`
  — an unclosed `[alice_` is left as plain text until the next
  delta completes it.
- **Survives tables and lists.** `renderWithCitations` is called
  from component overrides on `td`, `th`, `li`, etc. — not just
  paragraphs. A citation inside a table cell still renders as a
  chip.

### `CitationMarker`

- Shadcn `<Tooltip>` showing filename + section_heading + snippet.
- Click → scroll to `qa-source-{messageId}-{index}` → brief
  `ring-primary` flash.

### `<HighlightedText>`

Takes `text` + `match_spans`. Emits a sequence of plain text
and `<mark>` elements. No HTML traverses the wire — XSS surface
is closed at the API boundary (F92.1).

---

## Confidence + intent

`done` event payload (`api/rag-stream.ts::StreamDone`):

```typescript
{
  model: string,
  query_time_ms: number,
  confidence: "high" | "medium" | "low" | null,
  intent: Intent,                    // always defined
  intent_confidence: number,
}
```

UI rendering:

- `confidence` null → hide the badge entirely. Reflects the sentinel
  path ("Not in the provided documents.") — pretending to have "low"
  confidence would be worse than no badge.
- `confidence` `"high"|"medium"|"low"` → coloured Badge next to
  `model · ms`.
- `intent` available for future per-intent styling (icons, coloured
  borders). Not rendered today.

---

## Error UX

- Pre-stream 401/503 → `streamRagAnswer` throws → UI surfaces
  error toast via `extractApiError`.
- Mid-stream `error` event:
  - `llm_rate_limited` → message "too many requests, try again" +
    `details.retry_after_seconds` if present.
  - `llm_timeout` → "try again in a moment."
  - `llm_unavailable` → "provider unavailable."
  - `llm_error` (unknown) → generic "failed while generating."

Today the frontend shows a toast + the partial assistant message
stays whatever made it through. F92.11 is the follow-up to polish
these to retry buttons + countdowns.

---

## Known issues / pain points

1. **`parseSegments` only walks top-level string children.** Deeply
   nested markdown (bold inside list inside table) can hide citations
   if the library wraps strings in multiple nodes. Today the prompt
   encourages flat structures; not a production issue but fragile.
2. **Citation chip isn't keyboard-focusable** in a first-class way
   — it's a `<button>` but without a defined interaction for
   keyboard-only scroll-to. A11y gap.
3. **Scroll-to-source flash uses a ring class that gets cleared
   after timeout.** If the user scrolls elsewhere during the flash,
   the timeout still fires and may re-ring a different card
   accidentally. Low-impact.
4. **Typing indicator disappears as soon as the first delta
   lands** — sometimes the first delta is just whitespace, so the
   user sees "nothing" for a moment. Minor.
5. **Token storage for auth.** `getAccessToken()` reads from where
   the request interceptor stored it; if tokens are httpOnly-cookie
   only, `Authorization` header injection needs a different path.
   Check against the deployed auth pattern.
6. **SSE buffer is unbounded.** A pathological infinite stream
   (never sending `\n\n`) would grow `buffer` without bound. Our
   backend always closes; adversarial server would be a small leak.
7. **No reconnection logic.** If the connection drops mid-stream,
   we don't retry. The user sees a partial answer + toast.
8. **ReactMarkdown re-renders on every delta.** For a long answer
   with complex markdown, this is N markdown-parse cycles where N
   is #deltas. Works today (fast enough); a throttle would be nice.
9. **Citation-mapping is by filename.** Two different documents
   with the same filename (e.g. two `resume.pdf` uploads) both
   collide to the first SourceCitation. The backend dedupes by
   `document_id` but the frontend bracket-parser can't see that.
10. **Source panel shows even when all citations are the same
    doc chunk.** No collapse / grouping by document. Scales poorly
    once answers pull 10+ chunks from one doc.
11. **No export / copy affordance yet** (F92.4 scope). Users can
    select text but no "copy markdown" / "copy as plain text"
    buttons.
12. **Intent is observability-only.** No visual treatment per
    intent ("count" → bigger number at top; "comparison" → sticky
    table header). Leaves the answer less scannable than it could
    be.

---

## Improvement opportunities

### Short-term

- **Throttle `setState` on delta** via `requestAnimationFrame` or a
  small buffer (every 50ms). Same visual feel, fewer re-renders.
- **Stable citation IDs.** Have the backend include a
  `citation_id` on each `SourceCitation` (hash of
  `document_id:chunk_index`) and match against that instead of
  filename. Closes the same-filename collision class.
- **Keyboard scroll-to** — pressing Enter on a focused citation
  chip should scroll + flash + return focus to the source card's
  close button.

### Medium-term

- **Grouped source panel** — collapse multiple chunks from the same
  doc under a filename header with per-chunk subentries.
- **Copy buttons per message + whole-conversation export** (F92.4).
  Trivial once UI has actions row.
- **Regenerate button per message** (F92.5) — reuses the same
  question + optional style modifier.
- **Per-intent visual treatment.** `count` → big number; `yes_no` →
  banner at top; `ranking` → numbered cards. Leverage the
  intent field we already have on the wire.
- **Reconnection logic** with offset — on stream drop, POST again
  with a replay cursor so we don't regenerate what arrived. Needs
  backend support.

### Long-term

- **Streaming-aware markdown renderer** that parses incrementally
  rather than re-parsing on each delta. Custom parser; significant
  effort; pay only if profiling demands.
- **Citation-aware markdown component library** — swap shadcn
  table/list for a custom Citation-aware variant so we don't have
  to override 8 components for each renderer. Feels heavy until
  we have 3+ answer surfaces.
- **Offline / PWA support** — cache conversations and sources,
  show them when disconnected. Needs F96 persistent conversations
  first.

---

## Cross-references

- **Code**: `frontend/src/api/rag-stream.ts`,
  `frontend/src/pages/qa.tsx`,
  `frontend/src/components/highlighted-text.tsx`.
- **Backend wire contract**: `08-rag-pipeline.md`,
  `backend/app/schemas/rag.py`,
  `backend/app/api/routes/rag.py`.
- **Design**: `docs/features.md` F81.a/h/j (shipped),
  F92.3/4/5/6/7/11 (frontend polish todo),
  `docs/rag-system.md` §9.

---

## What changed

- **F92.2 — Stop button wired.** `qa.tsx` holds an `abortRef`
  (`AbortController`), passes `signal` into `streamRagAnswer`, and
  renders a `SquareIcon` Stop button in the `Composer` (`onStop` →
  `stop()`) while a generation is in flight. An aborted stream
  surfaces `AbortError`, and the partial assistant message falls
  back to `_Stopped._` when it has no content.
