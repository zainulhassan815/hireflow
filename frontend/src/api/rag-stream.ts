/**
 * Client for `POST /api/rag/stream`.
 *
 * The generated SDK can't consume SSE — openapi-ts only emits an SSE
 * consumer when the OpenAPI response declares a schema under
 * `text/event-stream`, and expressing our discriminated-union event
 * type there pulls in FastAPI/Pydantic ceremony that's out of scope
 * for F81.a. So this file owns the wire format directly. It's small:
 * the whole parser is ~30 lines.
 *
 * Event sequence (see backend `app/schemas/rag.py`):
 *   citations  → fires once before any deltas (omitted on no-hits)
 *   delta      → fires many times, `.data` is a partial text fragment
 *   done       → terminal success, carries model + timing
 *   error      → terminal failure, carries the ErrorBody envelope
 */

import { baseUrl, getAccessToken } from "./client";
import type {
  ErrorBody,
  RagRequest,
  SourceCitation,
} from "./generated/types.gen";

export interface StreamDone {
  model: string;
  query_time_ms: number;
}

export type RagStreamEvent =
  | { event: "citations"; data: SourceCitation[] }
  | { event: "delta"; data: string }
  | { event: "done"; data: StreamDone }
  | { event: "error"; data: ErrorBody };

export interface RagStreamHandlers {
  onEvent: (event: RagStreamEvent) => void;
  onError?: (err: unknown) => void;
  signal?: AbortSignal;
}

/**
 * POST to `/api/rag/stream` and dispatch SSE events to `handlers.onEvent`.
 *
 * Resolves when the stream closes (`done` or `error` received, or the
 * connection drops). Rejects only on network/transport errors before
 * the stream opens — mid-stream server errors arrive as `error` events.
 */
export async function streamRagAnswer(
  request: RagRequest,
  handlers: RagStreamHandlers
): Promise<void> {
  const token = getAccessToken();
  const response = await fetch(`${baseUrl}/api/rag/stream`, {
    method: "POST",
    signal: handlers.signal,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(request),
  });

  if (!response.ok || !response.body) {
    // 401/503 etc. — read the standard JSON error envelope.
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { error?: ErrorBody };
      if (body.error?.message) message = body.error.message;
    } catch {
      // non-JSON response; keep generic message
    }
    throw new Error(message);
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value;

      // SSE frames are separated by blank lines. Normalize CRLF first.
      buffer = buffer.replace(/\r\n?/g, "\n");
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const parsed = parseFrame(frame);
        if (parsed) handlers.onEvent(parsed);
      }
    }
  } catch (err) {
    handlers.onError?.(err);
    throw err;
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(frame: string): RagStreamEvent | null {
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
    // `event:` and `id:` lines are ignored — the event discriminator
    // travels inside the JSON payload, so there's only one source of
    // truth to switch on.
  }
  if (!dataLines.length) return null;
  try {
    return JSON.parse(dataLines.join("\n")) as RagStreamEvent;
  } catch {
    return null;
  }
}
