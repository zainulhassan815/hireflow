"""Shared helpers for table-kind providers (F105.c).

Keeps row/column caps, MinIO key convention, and JSON shape in one
place so ``SpreadsheetProvider`` and ``CsvTsvProvider`` stay focused
on their format-specific parsing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from app.adapters.viewers.protocol import StoragePutSync

# Per-sheet caps to protect against malicious / accidental huge
# spreadsheets. A 10k × 100 sheet is ~1 MB JSON inline — comfortable
# browser-side. Bigger sheets truncate and set meta.truncated=True so
# the frontend can surface a "showing first N of M" hint.
MAX_ROWS_PER_SHEET = 10_000
MAX_COLS_PER_SHEET = 100


@dataclass(frozen=True)
class TableSheet:
    name: str
    headers: list[str]
    rows: list[list[str]]
    total_rows: int  # pre-truncation row count (data rows only, no header)
    total_cols: int  # pre-truncation col count

    @property
    def truncated(self) -> bool:
        return self.total_rows > len(self.rows) or self.total_cols > len(self.headers)


def table_viewable_key(doc_id: UUID) -> str:
    """MinIO key convention for the cached table JSON."""
    return f"viewable/{doc_id}.json"


def store_table_payload(
    *,
    doc_id: UUID,
    sheets: list[TableSheet],
    storage_put: StoragePutSync,
) -> str:
    """Serialise sheets to JSON, persist, return the key."""
    key = table_viewable_key(doc_id)
    payload = {
        "sheets": [
            {
                "name": s.name,
                "headers": s.headers,
                "rows": s.rows,
                "truncated": s.truncated,
                "total_rows": s.total_rows,
                "total_cols": s.total_cols,
            }
            for s in sheets
        ]
    }
    data = json.dumps(payload).encode("utf-8")
    storage_put(key, data, "application/json")
    return key


def truncate(rows: list[list[str]]) -> tuple[list[str], list[list[str]], int, int]:
    """Cap rows/columns; return (headers, data_rows, total_rows, total_cols).

    ``rows`` is the raw parsed sheet — first row becomes headers.
    Empty sheets return empty headers + rows.
    """
    if not rows:
        return [], [], 0, 0

    raw_headers = rows[0]
    raw_data = rows[1:]

    # String-ify headers; apply col cap. Preserve order.
    total_cols = len(raw_headers)
    capped_cols = min(total_cols, MAX_COLS_PER_SHEET)
    headers = [str(h) if h is not None else "" for h in raw_headers[:capped_cols]]

    total_rows = len(raw_data)
    capped_rows = min(total_rows, MAX_ROWS_PER_SHEET)
    data_rows = [
        [str(cell) if cell is not None else "" for cell in row[:capped_cols]]
        # Pad short rows so the frontend gets a rectangular grid.
        + [""] * max(0, capped_cols - len(row))
        for row in raw_data[:capped_rows]
    ]

    return headers, data_rows, total_rows, total_cols
