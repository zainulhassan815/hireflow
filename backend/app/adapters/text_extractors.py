"""Concrete text-extraction implementations.

Each extractor handles a subset of MIME types. ``CompositeExtractor``
dispatches to the first extractor that supports the given type.
"""

from __future__ import annotations

import io

from app.adapters.protocols import ExtractionResult
from app.domain.exceptions import UnsupportedFileType


class PdfExtractor:
    """Extract text from PDF files using PyMuPDF."""

    _MIME_TYPES = frozenset({"application/pdf"})

    def supports(self, mime_type: str) -> bool:
        return mime_type in self._MIME_TYPES

    def extract(self, data: bytes, mime_type: str) -> ExtractionResult:
        import pymupdf

        doc = pymupdf.open(stream=data, filetype="pdf")
        pages: list[str] = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return ExtractionResult(
            text="\n\n".join(pages).strip(),
            page_count=len(pages),
        )


class DocxExtractor:
    """Extract text from DOCX/DOC files using python-docx."""

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
    """Extract text from images using Tesseract OCR."""

    _MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/tiff"})

    def supports(self, mime_type: str) -> bool:
        return mime_type in self._MIME_TYPES

    def extract(self, data: bytes, mime_type: str) -> ExtractionResult:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(data))
        text: str = pytesseract.image_to_string(image)
        return ExtractionResult(text=text.strip())


class CompositeExtractor:
    """Dispatch to the first extractor that supports the given MIME type.

    This is the implementation wired into the service layer. Adding a new
    format means writing an extractor class and appending it to the list.
    """

    def __init__(self, extractors: list | None = None) -> None:
        self._extractors = extractors or [
            PdfExtractor(),
            DocxExtractor(),
            ImageExtractor(),
        ]

    def supports(self, mime_type: str) -> bool:
        return any(e.supports(mime_type) for e in self._extractors)

    def extract(self, data: bytes, mime_type: str) -> ExtractionResult:
        for extractor in self._extractors:
            if extractor.supports(mime_type):
                return extractor.extract(data, mime_type)
        raise UnsupportedFileType(f"No extractor for MIME type {mime_type!r}.")
