import * as React from "react";

import { cn } from "@/lib/utils";

interface HighlightedTextProps extends React.HTMLAttributes<HTMLSpanElement> {
  text: string;
  /**
   * Non-overlapping `[start, end)` offsets into `text` where query terms
   * matched, as returned by `/search` and `/rag/query`. Spans must be
   * sorted and non-overlapping (the backend guarantees this).
   */
  spans?: ReadonlyArray<readonly [number, number]>;
  markClassName?: string;
}

export function HighlightedText({
  text,
  spans,
  markClassName,
  className,
  ...props
}: HighlightedTextProps) {
  const segments = React.useMemo(
    () => buildSegments(text, spans ?? []),
    [text, spans]
  );

  return (
    <span className={className} {...props}>
      {segments.map((segment, idx) =>
        segment.match ? (
          <mark
            key={idx}
            className={cn(
              "text-foreground rounded-sm bg-yellow-200/70 px-0.5 dark:bg-yellow-300/30",
              markClassName
            )}
          >
            {segment.text}
          </mark>
        ) : (
          <React.Fragment key={idx}>{segment.text}</React.Fragment>
        )
      )}
    </span>
  );
}

interface Segment {
  text: string;
  match: boolean;
}

function buildSegments(
  text: string,
  spans: ReadonlyArray<readonly [number, number]>
): Segment[] {
  if (spans.length === 0 || text.length === 0) {
    return [{ text, match: false }];
  }

  const segments: Segment[] = [];
  let cursor = 0;

  for (const [start, end] of spans) {
    // Defensive: skip malformed spans rather than crashing the snippet.
    if (start < cursor || end <= start || start >= text.length) continue;
    if (start > cursor) {
      segments.push({ text: text.slice(cursor, start), match: false });
    }
    segments.push({
      text: text.slice(start, Math.min(end, text.length)),
      match: true,
    });
    cursor = Math.min(end, text.length);
  }

  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), match: false });
  }

  return segments;
}
