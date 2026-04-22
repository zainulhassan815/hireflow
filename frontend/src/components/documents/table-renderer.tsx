import * as React from "react";

import { Typography } from "@/components/ui/typography";

/**
 * F105.c — inline table view for `kind="table"` payloads.
 *
 * Handles single-sheet (CSV / TSV) and multi-sheet (xlsx) uniformly:
 * multi-sheet shows a tab strip, single-sheet skips the tabs. Header
 * row is sticky top, first column sticky left, body scrolls both
 * axes inside a max-height window.
 *
 * Deliberately NOT a full spreadsheet: no sort, no filter, no
 * formula evaluation. This is a viewer.
 */

interface TableSheet {
  name: string;
  headers: string[];
  rows: string[][];
  truncated?: boolean;
  total_rows?: number;
  total_cols?: number;
}

interface TablePayload {
  sheets: TableSheet[];
}

export function TableRenderer({ data }: { data: unknown }) {
  const payload = data as TablePayload | null | undefined;
  const sheets = payload?.sheets ?? [];
  const [activeIndex, setActiveIndex] = React.useState(0);

  if (sheets.length === 0) {
    return (
      <div className="bg-muted/40 rounded-lg border border-dashed p-6 text-center">
        <Typography variant="muted">No sheets in this file.</Typography>
      </div>
    );
  }

  const active = sheets[Math.min(activeIndex, sheets.length - 1)];
  const showTabs = sheets.length > 1;

  return (
    <div className="flex flex-col gap-2 rounded-lg border bg-white dark:bg-neutral-950">
      {showTabs ? (
        <div className="flex gap-1 overflow-x-auto border-b px-2 pt-2">
          {sheets.map((sheet, i) => (
            <button
              key={`${sheet.name}-${i}`}
              type="button"
              onClick={() => setActiveIndex(i)}
              className={`shrink-0 rounded-t px-3 py-1.5 text-sm font-medium transition-colors ${
                i === activeIndex
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted/60"
              }`}
            >
              {sheet.name || `Sheet ${i + 1}`}
            </button>
          ))}
        </div>
      ) : null}

      <div className="max-h-[560px] overflow-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="bg-muted/70 sticky top-0 z-10">
            <tr>
              {active.headers.map((h, i) => (
                <th
                  key={i}
                  className={`border-b px-3 py-2 text-left font-semibold whitespace-nowrap ${
                    i === 0 ? "bg-muted/70 sticky left-0 z-20" : ""
                  }`}
                >
                  {h || <span className="text-muted-foreground">—</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {active.rows.map((row, r) => (
              <tr key={r} className="hover:bg-muted/40 even:bg-muted/20">
                {row.map((cell, c) => (
                  <td
                    key={c}
                    className={`border-b px-3 py-1.5 align-top whitespace-pre-wrap ${
                      c === 0 ? "sticky left-0 bg-inherit font-medium" : ""
                    }`}
                  >
                    {cell || <span className="text-muted-foreground">·</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {active.truncated ? (
        <Typography variant="muted" className="px-3 pb-2 text-xs">
          Showing first {active.rows.length.toLocaleString()} of{" "}
          {(active.total_rows ?? active.rows.length).toLocaleString()} rows
          {active.total_cols && active.total_cols > active.headers.length
            ? ` · first ${active.headers.length} of ${active.total_cols} columns`
            : null}
          . Download the file for the full data.
        </Typography>
      ) : null}
    </div>
  );
}
