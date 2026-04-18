"""Concrete text-extraction implementations.

Each extractor handles a subset of MIME types. ``CompositeExtractor``
dispatches to the first extractor that supports the given type.
"""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

from app.adapters.protocols import ExtractionResult
from app.domain.exceptions import UnsupportedFileType

if TYPE_CHECKING:
    from app.adapters.protocols import VisionProvider

logger = logging.getLogger(__name__)

_SCANNED_PAGE_THRESHOLD = 50  # chars — below this we treat the page as scanned


class PdfExtractor:
    """Extract text from PDF files using PyMuPDF.

    Pages that yield fewer than ``_SCANNED_PAGE_THRESHOLD`` characters are
    treated as scanned: rendered to an image and delegated to the configured
    ``VisionProvider`` for OCR.
    """

    _MIME_TYPES = frozenset({"application/pdf"})

    def __init__(self, vision: VisionProvider | None = None) -> None:
        self._vision = vision

    def supports(self, mime_type: str) -> bool:
        return mime_type in self._MIME_TYPES

    def extract(self, data: bytes, mime_type: str) -> ExtractionResult:
        import pymupdf

        doc = pymupdf.open(stream=data, filetype="pdf")
        pages: list[str] = []

        for page in doc:
            text = page.get_text().strip()
            if len(text) >= _SCANNED_PAGE_THRESHOLD or self._vision is None:
                pages.append(text)
                continue
            try:
                pages.append(self._ocr_page(page))
            except Exception:
                # Don't fail the whole document because one page's OCR
                # blew up (tesseract missing, corrupt image, etc.).
                # Fall back to whatever sparse text the page did yield.
                logger.exception(
                    "OCR failed for page %d, falling back to native text",
                    page.number,
                )
                pages.append(text)

        page_count = len(pages)
        doc.close()
        return ExtractionResult(
            text="\n\n".join(pages).strip(),
            page_count=page_count,
        )

    def _ocr_page(self, page) -> str:  # type: ignore[no-untyped-def]
        """Render the page to a PNG and delegate to the vision provider."""
        assert self._vision is not None
        pix = page.get_pixmap(dpi=300)
        image_bytes = pix.tobytes("png")
        logger.info("page %d has sparse text, delegating to vision OCR", page.number)
        return self._vision.extract_text_from_image(image_bytes)


class DocxExtractor:
    """Extract text from DOCX files using python-docx."""

    _MIME_TYPES = frozenset(
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        }
    )

    def supports(self, mime_type: str) -> bool:
        return mime_type in self._MIME_TYPES

    def extract(self, data: bytes, mime_type: str) -> ExtractionResult:
        from docx import Document

        doc = Document(io.BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return ExtractionResult(text="\n\n".join(paragraphs).strip())


class ImageExtractor:
    """Extract text from images by delegating to the configured VisionProvider."""

    _MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/tiff"})

    def __init__(self, vision: VisionProvider) -> None:
        self._vision = vision

    def supports(self, mime_type: str) -> bool:
        return mime_type in self._MIME_TYPES

    def extract(self, data: bytes, mime_type: str) -> ExtractionResult:
        text = self._vision.extract_text_from_image(data)
        return ExtractionResult(text=text)


class CompositeExtractor:
    """Dispatch to the first extractor that supports the given MIME type.

    Wired in the Celery task with the runtime-resolved ``VisionProvider``.
    """

    def __init__(self, vision: VisionProvider | None = None) -> None:
        self._extractors = [
            PdfExtractor(vision=vision),
            DocxExtractor(),
        ]
        if vision is not None:
            self._extractors.append(ImageExtractor(vision=vision))

    def supports(self, mime_type: str) -> bool:
        return any(e.supports(mime_type) for e in self._extractors)

    def extract(self, data: bytes, mime_type: str) -> ExtractionResult:
        for extractor in self._extractors:
            if extractor.supports(mime_type):
                return extractor.extract(data, mime_type)
        raise UnsupportedFileType(f"No extractor for MIME type {mime_type!r}.")
