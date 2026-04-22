"""Office-to-PDF provider (F105.b).

Converts docx / doc / pptx / ppt / odt / odp / rtf uploads to a PDF
asset via LibreOffice's headless CLI. The converted blob lands in
MinIO at ``viewable/<doc_id>.pdf`` and its key is persisted on the
``Document`` row so the render path is a single MinIO signature.

Spreadsheet MIMEs (xlsx / xls / ods) are deliberately **not** handled
here — converting them to PDF would produce a screenshot-of-a-table,
which is worse UX than the real spreadsheet renderer F105.c will ship.

If LibreOffice isn't installed (dev machines without the binary),
``prepare`` raises ``LibreOfficeUnavailable``. The caller
(``ViewerPreparationService``) catches, logs, and leaves the
viewable columns NULL; the render path then returns ``unsupported``
with ``meta.reason = "conversion_pending"`` so the user sees a
download fallback instead of a broken iframe.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from app.adapters.protocols import BlobStorage
from app.adapters.viewers.protocol import (
    PreparationResult,
    StorageGetSync,
    StoragePutSync,
    ViewablePayload,
)
from app.core.config import settings
from app.models import Document

logger = logging.getLogger(__name__)

_OFFICE_MIME_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
        "application/msword",  # doc
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
        "application/vnd.ms-powerpoint",  # ppt
        "application/vnd.oasis.opendocument.text",  # odt
        "application/vnd.oasis.opendocument.presentation",  # odp
        "application/rtf",
        "text/rtf",
    }
)

# MIME → filename extension. LibreOffice infers format from extension, so
# the temp file we hand it must end in the right suffix. Unknown MIMEs
# in the accepted set fall back to ``.bin`` — LibreOffice rejects those,
# which is fine; we surface the error.
_EXT_BY_MIME: dict[str, str] = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.oasis.opendocument.text": ".odt",
    "application/vnd.oasis.opendocument.presentation": ".odp",
    "application/rtf": ".rtf",
    "text/rtf": ".rtf",
}

_URL_TTL_SECONDS = 3600


class LibreOfficeError(RuntimeError):
    """LibreOffice ran but didn't produce a usable PDF."""


class LibreOfficeUnavailable(LibreOfficeError):
    """The ``libreoffice`` binary isn't on PATH (or wherever config points).

    Distinct from a conversion failure so the caller can degrade
    differently — a missing binary on a dev machine shouldn't
    look like a broken pipeline.
    """


class OfficeToPdfProvider:
    """Converts office formats to PDF via LibreOffice, stores in MinIO."""

    def accepts(self, mime_type: str | None) -> bool:
        return mime_type in _OFFICE_MIME_TYPES

    def prepare(
        self,
        doc: Document,
        *,
        storage_get: StorageGetSync,
        storage_put: StoragePutSync,
    ) -> PreparationResult:
        source_bytes = storage_get(doc.storage_key)
        pdf_bytes = _convert_to_pdf(
            source_bytes=source_bytes,
            mime_type=doc.mime_type,
            bin_path=settings.libreoffice_bin,
            timeout_seconds=settings.libreoffice_convert_timeout_seconds,
        )
        viewable_key = f"viewable/{doc.id}.pdf"
        storage_put(viewable_key, pdf_bytes, "application/pdf")
        return PreparationResult(kind="pdf", key=viewable_key)

    async def render(self, doc: Document, storage: BlobStorage) -> ViewablePayload:
        if not doc.viewable_key:
            # Prep hasn't run yet (or ran and failed). Don't convert
            # on the HTTP path — too slow; the FastAPI worker would
            # block for seconds. Frontend shows a download fallback.
            return ViewablePayload(
                kind="unsupported",
                meta={
                    "mime_type": doc.mime_type,
                    "filename": doc.filename,
                    "reason": "conversion_pending",
                },
            )
        url = await storage.presigned_url(doc.viewable_key, _URL_TTL_SECONDS)
        return ViewablePayload(
            kind="pdf",
            url=url,
            meta={"source_mime_type": doc.mime_type},
        )


def _convert_to_pdf(
    *,
    source_bytes: bytes,
    mime_type: str,
    bin_path: str,
    timeout_seconds: int,
) -> bytes:
    """Run LibreOffice headless and return the produced PDF bytes.

    Subprocess-level concerns live here so ``OfficeToPdfProvider`` stays
    testable in isolation (mock ``subprocess.run``).
    """
    ext = _EXT_BY_MIME.get(mime_type, ".bin")

    with TemporaryDirectory(prefix="hireflow-office-") as tmp:
        tmp_path = Path(tmp)
        # LibreOffice is historically flaky with concurrent invocations
        # because it stores profile state under ``$HOME/.config``. Give
        # each conversion its own isolated profile directory via a
        # disposable HOME; keep PATH / locale from the parent so
        # ``libreoffice`` resolves the same way it would interactively.
        isolated_env = dict(os.environ)
        isolated_env["HOME"] = str(tmp_path)

        src_path = tmp_path / f"input{ext}"
        src_path.write_bytes(source_bytes)

        started = time.monotonic()
        try:
            result = subprocess.run(
                [
                    bin_path,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmp_path),
                    str(src_path),
                ],
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
                env=isolated_env,
            )
        except FileNotFoundError as exc:
            raise LibreOfficeUnavailable(
                f"{bin_path!r} not found on PATH; install libreoffice or "
                "set LIBREOFFICE_BIN"
            ) from exc

        elapsed_ms = int((time.monotonic() - started) * 1000)

        if result.returncode != 0:
            raise LibreOfficeError(
                f"libreoffice exited {result.returncode}: "
                f"{result.stderr.decode(errors='ignore')[:500]}"
            )

        # LibreOffice keeps the basename, swaps extension to .pdf.
        pdf_path = src_path.with_suffix(".pdf")
        if not pdf_path.exists():
            raise LibreOfficeError("libreoffice exited 0 but no PDF was produced")

        pdf_bytes = pdf_path.read_bytes()

    logger.info(
        "office → pdf: source_mime=%s source_bytes=%d output_bytes=%d elapsed_ms=%d",
        mime_type,
        len(source_bytes),
        len(pdf_bytes),
        elapsed_ms,
    )
    return pdf_bytes
