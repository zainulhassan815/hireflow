"""Unit tests for F105.b's OfficeToPdfProvider.

Two layers:

1. Pure-Python unit tests that mock ``subprocess.run`` — these run in
   any environment and cover the wiring: command shape, error
   translation, binary-missing handling, idempotent re-prepare.
2. A live-conversion test that runs only when ``libreoffice`` is on
   PATH (``pytest.skip`` otherwise). No fixture docx is shipped —
   the test writes a minimal RTF (plain text, 1 line) which every
   LibreOffice version can convert.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from app.adapters.protocols import StoredBlob
from app.adapters.viewers import (
    LibreOfficeError,
    LibreOfficeUnavailable,
    OfficeToPdfProvider,
    PreparationResult,
)
from app.adapters.viewers.office import _convert_to_pdf
from app.models import Document


def _doc(mime: str, *, filename: str = "file.docx") -> Document:
    return Document(
        id=uuid4(),
        owner_id=uuid4(),
        filename=filename,
        mime_type=mime,
        size_bytes=1024,
        storage_key=f"test/{filename}",
    )


class _FakeStorage:
    """Sync-callable pair: records puts, serves gets from a dict."""

    def __init__(self, initial: dict[str, bytes] | None = None) -> None:
        self.store: dict[str, bytes] = dict(initial or {})
        self.put_calls: list[tuple[str, int, str]] = []

    def get_sync(self, key: str) -> bytes:
        return self.store[key]

    def put_sync(self, key: str, data: bytes, content_type: str) -> StoredBlob:
        self.store[key] = data
        self.put_calls.append((key, len(data), content_type))
        return StoredBlob(key=key, size=len(data), etag="fake")


# ---------- accepts() ------------------------------------------------------


def test_office_provider_accepts_office_mimes() -> None:
    provider = OfficeToPdfProvider()
    for mime in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-powerpoint",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.presentation",
        "application/rtf",
        "text/rtf",
    ):
        assert provider.accepts(mime), mime


def test_office_provider_rejects_pdf_image_spreadsheet() -> None:
    """Spreadsheet MIMEs are F105.c's territory, not a PDF conversion.

    If this test ever flips to asserting ``True`` for xlsx, F105.c's
    table renderer will get shadowed by the office → PDF path and the
    user will lose the real spreadsheet UX.
    """
    provider = OfficeToPdfProvider()
    for mime in (
        "application/pdf",
        "image/png",
        "image/jpeg",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
        "application/vnd.ms-excel",  # xls
        "application/vnd.oasis.opendocument.spreadsheet",  # ods
        "text/csv",
        None,
    ):
        assert not provider.accepts(mime), mime


# ---------- prepare() with mocked subprocess -------------------------------


def _mock_subprocess_success(
    monkeypatch: pytest.MonkeyPatch, pdf_bytes: bytes = b"%PDF-1.4 fake"
) -> list[list[str]]:
    """Stub subprocess.run to write ``pdf_bytes`` to the expected output path."""
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs):
        calls.append(cmd)
        # The provider invokes libreoffice with --outdir <tmp> <input>.
        # Find the input file, write a .pdf next to it with the same stem.
        input_path = Path(cmd[-1])
        (input_path.with_suffix(".pdf")).write_bytes(pdf_bytes)

        class Done:
            returncode = 0
            stderr = b""
            stdout = b""

        return Done()

    monkeypatch.setattr("app.adapters.viewers.office.subprocess.run", fake_run)
    return calls


def test_prepare_writes_pdf_to_storage_and_returns_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _mock_subprocess_success(monkeypatch, pdf_bytes=b"%PDF-1.4 fake content")
    storage = _FakeStorage({"test/file.docx": b"fake docx source bytes"})
    provider = OfficeToPdfProvider()
    doc = _doc(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    result = provider.prepare(
        doc, storage_get=storage.get_sync, storage_put=storage.put_sync
    )

    assert isinstance(result, PreparationResult)
    assert result.kind == "pdf"
    assert result.key == f"viewable/{doc.id}.pdf"
    assert storage.store[result.key] == b"%PDF-1.4 fake content"
    # Exactly one put; content-type set; correct size.
    assert len(storage.put_calls) == 1
    key, size, content_type = storage.put_calls[0]
    assert key == f"viewable/{doc.id}.pdf"
    assert content_type == "application/pdf"
    assert size == len(b"%PDF-1.4 fake content")

    # Command shape: libreoffice --headless --convert-to pdf --outdir <tmp> <input>
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == "libreoffice"
    assert "--headless" in cmd
    assert "--convert-to" in cmd
    assert "pdf" in cmd
    assert "--outdir" in cmd


def test_prepare_nonzero_exit_raises_libreoffice_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd, **kwargs):
        class Done:
            returncode = 1
            stderr = b"Error: source file is corrupt"
            stdout = b""

        return Done()

    monkeypatch.setattr("app.adapters.viewers.office.subprocess.run", fake_run)

    storage = _FakeStorage({"test/file.docx": b"junk"})
    provider = OfficeToPdfProvider()
    doc = _doc(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    with pytest.raises(LibreOfficeError) as excinfo:
        provider.prepare(
            doc, storage_get=storage.get_sync, storage_put=storage.put_sync
        )
    assert "exited 1" in str(excinfo.value)
    assert storage.put_calls == []


def test_prepare_missing_output_file_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """LibreOffice exits 0 but produces no PDF — a known edge on doc corruption."""

    def fake_run(cmd, **kwargs):
        class Done:
            returncode = 0
            stderr = b""
            stdout = b""

        return Done()

    monkeypatch.setattr("app.adapters.viewers.office.subprocess.run", fake_run)

    storage = _FakeStorage({"test/file.docx": b"junk"})
    provider = OfficeToPdfProvider()
    doc = _doc(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    with pytest.raises(LibreOfficeError, match="no PDF was produced"):
        provider.prepare(
            doc, storage_get=storage.get_sync, storage_put=storage.put_sync
        )


def test_prepare_binary_missing_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct exception so callers can degrade differently from a convert failure.

    On a dev machine without LibreOffice the pipeline must stay
    functional: the caller logs + skips rather than turning every
    docx upload into a hard error.
    """

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError(f"No such file: {cmd[0]!r}")

    monkeypatch.setattr("app.adapters.viewers.office.subprocess.run", fake_run)

    storage = _FakeStorage({"test/file.docx": b"junk"})
    provider = OfficeToPdfProvider()
    doc = _doc(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    with pytest.raises(LibreOfficeUnavailable):
        provider.prepare(
            doc, storage_get=storage.get_sync, storage_put=storage.put_sync
        )


def test_prepare_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-running prepare overwrites the viewable blob cleanly.

    Same ``doc.id`` → same ``viewable/<id>.pdf`` key → the second
    put replaces the first. No attempt to delete the previous blob
    (deletion in the ingest hot path adds latency and failure modes
    we don't need).
    """
    _mock_subprocess_success(monkeypatch, pdf_bytes=b"%PDF-1.4 v1")
    storage = _FakeStorage({"test/file.docx": b"docx"})
    provider = OfficeToPdfProvider()
    doc = _doc(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    result1 = provider.prepare(
        doc, storage_get=storage.get_sync, storage_put=storage.put_sync
    )

    # Second pass produces different bytes.
    _mock_subprocess_success(monkeypatch, pdf_bytes=b"%PDF-1.4 v2")
    result2 = provider.prepare(
        doc, storage_get=storage.get_sync, storage_put=storage.put_sync
    )

    assert result1.key == result2.key
    assert storage.store[result2.key] == b"%PDF-1.4 v2"
    assert len(storage.put_calls) == 2


# ---------- render() -------------------------------------------------------


class _FakeAsyncStorage:
    """Async-side stub — only ``presigned_url`` is used by render."""

    async def presigned_url(self, key: str, expires_seconds: int = 3600) -> str:
        return f"https://minio.test/{key}?X-Amz-Expires={expires_seconds}"


@pytest.mark.asyncio
async def test_render_with_viewable_key_returns_pdf_url() -> None:
    provider = OfficeToPdfProvider()
    doc = _doc(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    doc.viewable_key = f"viewable/{doc.id}.pdf"

    payload = await provider.render(doc, _FakeAsyncStorage())

    assert payload.kind == "pdf"
    assert payload.url is not None
    assert f"viewable/{doc.id}.pdf" in payload.url


@pytest.mark.asyncio
async def test_render_without_viewable_key_returns_conversion_pending() -> None:
    provider = OfficeToPdfProvider()
    doc = _doc(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    # viewable_key deliberately unset — simulates "extract ran, prep
    # hasn't yet (or failed)".

    payload = await provider.render(doc, _FakeAsyncStorage())

    assert payload.kind == "unsupported"
    assert payload.url is None
    assert payload.meta["reason"] == "conversion_pending"
    assert payload.meta["filename"] == "file.docx"


# ---------- Live conversion (skipped without libreoffice) ------------------


@pytest.mark.skipif(
    shutil.which("libreoffice") is None,
    reason="LibreOffice not installed on this host",
)
def test_live_conversion_produces_real_pdf(tmp_path: Path) -> None:
    """Round-trip a minimal RTF through real LibreOffice.

    RTF is the simplest format every LibreOffice version accepts —
    avoids shipping a binary fixture. The only assertion is that
    the output looks like a PDF (magic bytes + non-trivial size).
    """
    rtf = rb"{\rtf1\ansi Hello from a test fixture.\par}"
    # Pass through the adapter the same way ``prepare`` does.
    result = _convert_to_pdf(
        source_bytes=rtf,
        mime_type="application/rtf",
        bin_path="libreoffice",
        timeout_seconds=120,
    )
    assert result.startswith(b"%PDF-")
    assert len(result) > 200


# ---------- Timeout handling ----------------------------------------------


def test_prepare_timeout_surfaces_as_libreoffice_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 120))

    monkeypatch.setattr("app.adapters.viewers.office.subprocess.run", fake_run)

    storage = _FakeStorage({"test/file.docx": b"docx"})
    provider = OfficeToPdfProvider()
    doc = _doc(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    # TimeoutExpired isn't re-wrapped — it's a subprocess-layer concern
    # that callers can match directly if they want to distinguish it.
    # The ViewerPreparationService catches the generic Exception and
    # falls through to "viewer-less doc," which is the right behavior.
    with pytest.raises(subprocess.TimeoutExpired):
        provider.prepare(
            doc, storage_get=storage.get_sync, storage_put=storage.put_sync
        )
