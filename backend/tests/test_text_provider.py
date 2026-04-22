"""Unit tests for F105.d's TextProvider."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.adapters.protocols import StoredBlob
from app.adapters.viewers import TextProvider
from app.models import Document


def _doc(mime: str, *, filename: str, size: int = 100) -> Document:
    return Document(
        id=uuid4(),
        owner_id=uuid4(),
        filename=filename,
        mime_type=mime,
        size_bytes=size,
        storage_key=f"test/{filename}",
    )


class _FakeAsync:
    def __init__(self, store: dict[str, bytes]) -> None:
        self._store = store

    async def get(self, key: str) -> bytes:
        return self._store[key]

    async def presigned_url(self, *_args, **_kwargs) -> str:
        raise AssertionError("text provider shouldn't sign URLs")


@pytest.mark.parametrize(
    "mime,expected",
    [
        ("text/plain", True),
        ("text/markdown", True),
        ("text/x-markdown", True),
        ("application/x-log", True),
        ("text/csv", False),  # F105.c's CsvTsvProvider handles this
        ("text/tab-separated-values", False),
        ("application/pdf", False),
        (None, False),
    ],
)
def test_accepts_boundaries(mime: str | None, expected: bool) -> None:
    assert TextProvider().accepts(mime) is expected


def test_prepare_records_source_key_as_viewable() -> None:
    """Text providers don't convert; source bytes ARE the viewable."""

    def _fake_get(_: str) -> bytes:
        raise AssertionError("text.prepare shouldn't fetch blob bytes")

    def _fake_put(*_args) -> StoredBlob:
        raise AssertionError("text.prepare shouldn't write blobs")

    doc = _doc("text/markdown", filename="README.md")
    result = TextProvider().prepare(doc, storage_get=_fake_get, storage_put=_fake_put)
    assert result.kind == "text"
    assert result.key == doc.storage_key


@pytest.mark.asyncio
async def test_render_markdown_sets_format() -> None:
    doc = _doc("text/markdown", filename="README.md")
    storage = _FakeAsync({doc.storage_key: b"# Heading\n\nBody."})

    payload = await TextProvider().render(doc, storage)

    assert payload.kind == "text"
    assert payload.data["content"] == "# Heading\n\nBody."
    assert payload.data["format"] == "markdown"
    assert payload.meta["filename"] == "README.md"


@pytest.mark.asyncio
async def test_render_plain_sets_format() -> None:
    doc = _doc("text/plain", filename="notes.txt")
    storage = _FakeAsync({doc.storage_key: b"just some notes"})

    payload = await TextProvider().render(doc, storage)

    assert payload.kind == "text"
    assert payload.data["format"] == "plain"


@pytest.mark.asyncio
async def test_render_uses_viewable_key_when_set() -> None:
    doc = _doc("text/plain", filename="x.txt")
    doc.viewable_key = "alternative/path.txt"
    storage = _FakeAsync({"alternative/path.txt": b"from viewable key"})

    payload = await TextProvider().render(doc, storage)
    assert payload.data["content"] == "from viewable key"


@pytest.mark.asyncio
async def test_render_non_utf8_bytes_survive() -> None:
    """Rogue latin-1 byte gets replaced, not crashed."""
    doc = _doc("text/plain", filename="mixed.txt")
    storage = _FakeAsync({doc.storage_key: b"hello \xff world"})

    payload = await TextProvider().render(doc, storage)
    assert payload.kind == "text"
    assert "hello" in payload.data["content"]
    assert "world" in payload.data["content"]


@pytest.mark.asyncio
async def test_render_refuses_oversized_files() -> None:
    """Files over 5 MB fall through to unsupported with a reason."""
    doc = _doc("text/plain", filename="huge.txt", size=10 * 1024 * 1024)
    storage = _FakeAsync({})  # shouldn't be read

    payload = await TextProvider().render(doc, storage)
    assert payload.kind == "unsupported"
    assert payload.meta["reason"] == "too_large_to_inline"
    assert payload.meta["size_bytes"] == 10 * 1024 * 1024
    assert payload.meta["limit_bytes"] == 5 * 1024 * 1024
