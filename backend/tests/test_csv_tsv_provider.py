"""Unit tests for F105.c's CsvTsvProvider."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.adapters.protocols import StoredBlob
from app.adapters.viewers import CsvTsvProvider
from app.models import Document


def _doc(mime: str, *, filename: str) -> Document:
    return Document(
        id=uuid4(),
        owner_id=uuid4(),
        filename=filename,
        mime_type=mime,
        size_bytes=100,
        storage_key=f"test/{filename}",
    )


class _FakeStorage:
    def __init__(self, initial: dict[str, bytes] | None = None) -> None:
        self.store: dict[str, bytes] = dict(initial or {})

    def get_sync(self, key: str) -> bytes:
        return self.store[key]

    def put_sync(self, key: str, data: bytes, content_type: str) -> StoredBlob:
        self.store[key] = data
        return StoredBlob(key=key, size=len(data), etag="fake")


@pytest.mark.parametrize(
    "mime,expected",
    [
        ("text/csv", True),
        ("application/csv", True),
        ("text/tab-separated-values", True),
        ("text/tsv", True),
        ("application/pdf", False),
        ("text/plain", False),  # plain text is F105.d's territory
        (None, False),
    ],
)
def test_accepts_boundaries(mime: str | None, expected: bool) -> None:
    assert CsvTsvProvider().accepts(mime) is expected


def test_csv_parse_round_trip() -> None:
    source = b"name,role\nAlice,Engineer\nBob,Designer\n"
    storage = _FakeStorage({"test/team.csv": source})
    doc = _doc("text/csv", filename="team.csv")

    result = CsvTsvProvider().prepare(
        doc, storage_get=storage.get_sync, storage_put=storage.put_sync
    )

    payload = json.loads(storage.store[result.key].decode("utf-8"))
    sheet = payload["sheets"][0]
    assert sheet["name"] == "team"
    assert sheet["headers"] == ["name", "role"]
    assert sheet["rows"] == [["Alice", "Engineer"], ["Bob", "Designer"]]


def test_tsv_delimiter_dispatch() -> None:
    source = b"a\tb\nc\td\n"
    storage = _FakeStorage({"test/x.tsv": source})
    doc = _doc("text/tab-separated-values", filename="x.tsv")

    CsvTsvProvider().prepare(
        doc, storage_get=storage.get_sync, storage_put=storage.put_sync
    )

    sheet = json.loads(storage.store[f"viewable/{doc.id}.json"].decode("utf-8"))[
        "sheets"
    ][0]
    assert sheet["headers"] == ["a", "b"]
    assert sheet["rows"] == [["c", "d"]]


def test_csv_quoted_fields_preserve_commas() -> None:
    source = b'name,bio\n"Alice","Engineer, NYC"\n'
    storage = _FakeStorage({"test/x.csv": source})
    doc = _doc("text/csv", filename="x.csv")

    CsvTsvProvider().prepare(
        doc, storage_get=storage.get_sync, storage_put=storage.put_sync
    )

    sheet = json.loads(storage.store[f"viewable/{doc.id}.json"].decode("utf-8"))[
        "sheets"
    ][0]
    assert sheet["rows"] == [["Alice", "Engineer, NYC"]]


def test_csv_non_utf8_bytes_survive() -> None:
    """Latin-1 rogue byte shouldn't crash the prep step.

    ``errors="replace"`` means one cell shows the replacement char
    rather than the whole sheet failing.
    """
    # 0xff is invalid UTF-8; triggers the errors="replace" path.
    source = b"name\n\xff\n"
    storage = _FakeStorage({"test/x.csv": source})
    doc = _doc("text/csv", filename="x.csv")

    result = CsvTsvProvider().prepare(
        doc, storage_get=storage.get_sync, storage_put=storage.put_sync
    )

    payload = json.loads(storage.store[result.key].decode("utf-8"))
    assert payload["sheets"][0]["headers"] == ["name"]
    assert len(payload["sheets"][0]["rows"]) == 1


@pytest.mark.asyncio
async def test_render_inlines_cached_json() -> None:
    source = b"a,b\n1,2\n"
    provider = CsvTsvProvider()
    doc = _doc("text/csv", filename="x.csv")
    doc.viewable_key = f"viewable/{doc.id}.json"
    sync_store = _FakeStorage({"test/x.csv": source})
    provider.prepare(
        doc, storage_get=sync_store.get_sync, storage_put=sync_store.put_sync
    )

    class _AsyncStorage:
        def __init__(self, store):
            self._store = store

        async def get(self, key: str) -> bytes:
            return self._store[key]

        async def presigned_url(self, *args, **kwargs):
            raise AssertionError("tables use inline data")

    payload = await provider.render(doc, _AsyncStorage(sync_store.store))
    assert payload.kind == "table"
    assert payload.data["sheets"][0]["headers"] == ["a", "b"]
