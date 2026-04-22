"""CSV / TSV → table provider (F105.c).

Uses the stdlib ``csv`` module. Shares the JSON shape +
row/column caps with ``SpreadsheetProvider`` so the frontend table
branch handles single-sheet CSVs and multi-sheet xlsx uniformly.
"""

from __future__ import annotations

import csv
import io
import json
import logging

from app.adapters.protocols import BlobStorage
from app.adapters.viewers._table_shape import (
    TableSheet,
    store_table_payload,
    truncate,
)
from app.adapters.viewers.protocol import (
    PreparationResult,
    StorageGetSync,
    StoragePutSync,
    ViewablePayload,
)
from app.models import Document

logger = logging.getLogger(__name__)

_CSV_MIMES = frozenset({"text/csv", "application/csv"})
_TSV_MIMES = frozenset({"text/tab-separated-values", "text/tsv"})


class CsvTsvProvider:
    def accepts(self, mime_type: str | None) -> bool:
        return mime_type in _CSV_MIMES or mime_type in _TSV_MIMES

    def prepare(
        self,
        doc: Document,
        *,
        storage_get: StorageGetSync,
        storage_put: StoragePutSync,
    ) -> PreparationResult:
        source = storage_get(doc.storage_key)
        delimiter = "\t" if doc.mime_type in _TSV_MIMES else ","
        sheet = self._parse(source, delimiter=delimiter, filename=doc.filename)
        key = store_table_payload(
            doc_id=doc.id, sheets=[sheet], storage_put=storage_put
        )
        logger.info(
            "%s → table: source_bytes=%d rows=%d cols=%d",
            "tsv" if delimiter == "\t" else "csv",
            len(source),
            sheet.total_rows,
            sheet.total_cols,
        )
        return PreparationResult(kind="table", key=key)

    async def render(self, doc: Document, storage: BlobStorage) -> ViewablePayload:
        if not doc.viewable_key:
            return ViewablePayload(
                kind="unsupported",
                meta={
                    "mime_type": doc.mime_type,
                    "filename": doc.filename,
                    "reason": "conversion_pending",
                },
            )
        blob = await storage.get(doc.viewable_key)
        data = json.loads(blob.decode("utf-8"))
        return ViewablePayload(
            kind="table",
            data=data,
            meta={"filename": doc.filename, "sheet_count": 1},
        )

    @staticmethod
    def _parse(source_bytes: bytes, *, delimiter: str, filename: str) -> TableSheet:
        # ``errors="replace"`` so a latin-1 CSV with a rogue byte
        # doesn't 500 the entire prep — the user sees one replacement
        # char rather than a hard fail.
        text = source_bytes.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        raw_rows = [list(row) for row in reader]
        headers, data_rows, total_rows, total_cols = truncate(raw_rows)
        # Sheet name is cosmetic for CSVs; use the filename stem so
        # the frontend tab strip (single tab here) reads naturally.
        sheet_name = filename.rsplit(".", 1)[0] or "Sheet 1"
        return TableSheet(
            name=sheet_name,
            headers=headers,
            rows=data_rows,
            total_rows=total_rows,
            total_cols=total_cols,
        )
