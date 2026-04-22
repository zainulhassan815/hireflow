"""Unit tests for the ViewerProvider registry + providers.

Pure functions — no DB, no MinIO. These pin the ``accepts()``
boundaries that control which provider handles which MIME, because
order-dependent dispatch is exactly the kind of thing that regresses
silently (new provider inserted below fallback → never runs; new MIME
overlaps → first-match wins the wrong one).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.adapters.viewers import (
    CsvTsvProvider,
    FallbackProvider,
    OfficeToPdfProvider,
    PassthroughImageProvider,
    PassthroughPdfProvider,
    PreparationResult,
    SpreadsheetProvider,
    ViewerRegistry,
    build_default_registry,
)
from app.models import Document


def _doc(mime: str, *, filename: str = "x", storage_key: str = "k") -> Document:
    """Minimal in-memory Document; not persisted."""
    return Document(
        id=uuid4(),
        owner_id=uuid4(),
        filename=filename,
        mime_type=mime,
        size_bytes=100,
        storage_key=storage_key,
    )


class _FakeStorage:
    """BlobStorage stub — only ``presigned_url`` is used by passthroughs."""

    async def presigned_url(self, key: str, expires_seconds: int = 3600) -> str:
        return f"https://minio.test/{key}?X-Amz-Expires={expires_seconds}"


def test_pdf_provider_accepts_only_pdf() -> None:
    provider = PassthroughPdfProvider()
    assert provider.accepts("application/pdf") is True
    assert provider.accepts("image/png") is False
    assert provider.accepts(None) is False
    assert provider.accepts("application/octet-stream") is False


def test_image_provider_accepts_configured_set() -> None:
    provider = PassthroughImageProvider()
    for mime in ("image/png", "image/jpeg", "image/tiff", "image/webp", "image/gif"):
        assert provider.accepts(mime) is True, mime
    assert provider.accepts("image/x-icon") is False
    assert provider.accepts("application/pdf") is False
    assert provider.accepts(None) is False


def test_fallback_accepts_everything() -> None:
    provider = FallbackProvider()
    assert provider.accepts("application/pdf") is True
    assert provider.accepts("application/octet-stream") is True
    assert provider.accepts(None) is True


def test_default_registry_dispatch() -> None:
    registry = build_default_registry()
    assert isinstance(registry.for_mime("application/pdf"), PassthroughPdfProvider)
    assert isinstance(registry.for_mime("image/png"), PassthroughImageProvider)
    assert isinstance(
        registry.for_mime(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        OfficeToPdfProvider,
    )
    assert isinstance(
        registry.for_mime(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
        OfficeToPdfProvider,
    )
    # F105.c — spreadsheet MIMEs now hit the real spreadsheet provider,
    # not fallback.
    assert isinstance(
        registry.for_mime(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        SpreadsheetProvider,
    )
    # CSV / TSV also F105.c — text/csv is NOT owned by the text provider
    # (F105.d) because a table renderer is better UX than a raw text dump.
    assert isinstance(registry.for_mime("text/csv"), CsvTsvProvider)
    assert isinstance(registry.for_mime("text/tab-separated-values"), CsvTsvProvider)
    assert isinstance(registry.for_mime("application/zip"), FallbackProvider)
    # None slips through to fallback, not a crash.
    assert isinstance(registry.for_mime(None), FallbackProvider)


def test_passthrough_prepare_returns_source_key() -> None:
    """Passthroughs don't convert — ``prepare`` records source key + kind."""
    doc = Document(
        id=uuid4(),
        owner_id=uuid4(),
        filename="a.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        storage_key="owner/a.pdf",
    )

    def _fake_get(_: str) -> bytes:  # unused by passthroughs
        raise AssertionError("passthrough.prepare must not read source bytes")

    def _fake_put(*_args):  # unused by passthroughs
        raise AssertionError("passthrough.prepare must not write blobs")

    result = PassthroughPdfProvider().prepare(
        doc, storage_get=_fake_get, storage_put=_fake_put
    )
    assert result == PreparationResult(kind="pdf", key="owner/a.pdf")

    doc.mime_type = "image/png"
    doc.filename = "a.png"
    doc.storage_key = "owner/a.png"
    result = PassthroughImageProvider().prepare(
        doc, storage_get=_fake_get, storage_put=_fake_put
    )
    assert result == PreparationResult(kind="image", key="owner/a.png")


def test_fallback_prepare_returns_unsupported() -> None:
    doc = Document(
        id=uuid4(),
        owner_id=uuid4(),
        filename="x.zip",
        mime_type="application/zip",
        size_bytes=10,
        storage_key="owner/x.zip",
    )
    result = FallbackProvider().prepare(
        doc,
        storage_get=lambda _: b"",
        storage_put=lambda *_args: None,  # type: ignore[arg-type]
    )
    assert result == PreparationResult(kind="unsupported", key=None)


def test_registry_order_is_load_bearing() -> None:
    """If someone puts FallbackProvider first, it shadows everything.

    This test exists to catch the "hey I alphabetized the registry"
    bug. It's not hypothetical — it's exactly what happens when
    ``build_default_registry`` gets a well-meaning refactor.
    """
    shadowed = ViewerRegistry([FallbackProvider(), PassthroughPdfProvider()])
    assert isinstance(shadowed.for_mime("application/pdf"), FallbackProvider)


def test_empty_registry_raises() -> None:
    empty = ViewerRegistry([])
    with pytest.raises(LookupError):
        empty.for_mime("application/pdf")


@pytest.mark.asyncio
async def test_pdf_provider_renders_pdf_with_url() -> None:
    provider = PassthroughPdfProvider()
    payload = await provider.render(_doc("application/pdf"), _FakeStorage())
    assert payload.kind == "pdf"
    assert payload.url is not None
    assert "X-Amz-Expires=3600" in payload.url
    assert payload.data is None
    assert payload.meta["size_bytes"] == 100


@pytest.mark.asyncio
async def test_image_provider_renders_image_with_url() -> None:
    provider = PassthroughImageProvider()
    payload = await provider.render(_doc("image/png"), _FakeStorage())
    assert payload.kind == "image"
    assert payload.url is not None
    assert payload.meta["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_fallback_provider_returns_unsupported() -> None:
    provider = FallbackProvider()
    payload = await provider.render(
        _doc("application/zip", filename="archive.zip"), _FakeStorage()
    )
    assert payload.kind == "unsupported"
    assert payload.url is None
    assert payload.meta["reason"] == "no_viewer_for_mime"
    assert payload.meta["filename"] == "archive.zip"
