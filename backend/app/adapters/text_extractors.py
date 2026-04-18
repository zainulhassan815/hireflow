"""Text extraction (F82.d: layout-aware via ``unstructured``).

``UnstructuredExtractor`` replaces the old PyMuPDF + python-docx pair.
One adapter handles PDF and DOCX (and most other formats unstructured
supports) with a single API.

Two strategies:

* ``fast`` — rule-based partitioning (font size, indentation, line
  grouping). Zero GPU, ~1s/page. Good default for CPU-only deployments.
* ``hi_res`` — runs a YOLOX-based layout detector + optional
  Table Transformer. 5-30s cold start (model load on first call),
  100-300ms/page on GPU. Required for scanned PDFs with reliable table
  structure.

Output is an ``ExtractionResult`` carrying:

* ``text`` — reading-order concatenation for FTS backwards compat.
* ``page_count``.
* ``elements`` — typed ``Element`` list (``Title``, ``NarrativeText``,
  ``ListItem``, ``Table``, …). Consumers that want structure use these;
  callers that just want text can keep using ``text``.

Image OCR still flows through the ``VisionProvider`` — unstructured's
own OCR is available via its ``ocr_only`` strategy but we already have
Tesseract wired for images, so we keep that path.
"""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Any

from app.adapters.protocols import Element, ExtractionResult
from app.domain.exceptions import UnsupportedFileType

if TYPE_CHECKING:
    from app.adapters.protocols import VisionProvider

logger = logging.getLogger(__name__)


_PDF_MIME = "application/pdf"
_DOCX_MIMES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }
)
_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/tiff"})


class UnstructuredExtractor:
    """Layout-aware extractor for PDF + DOCX via ``unstructured``.

    Single instance per worker. First ``hi_res`` call triggers model
    download + load (one-time ~5-30s), subsequent calls are fast.
    """

    def __init__(
        self,
        *,
        strategy: str = "hi_res",
        infer_table_structure: bool = True,
    ) -> None:
        if strategy not in ("fast", "hi_res", "auto"):
            raise ValueError(
                f"Unknown extraction strategy {strategy!r}. "
                "Expected: fast, hi_res, auto."
            )
        self._strategy = strategy
        self._infer_table_structure = infer_table_structure

    def supports(self, mime_type: str) -> bool:
        return mime_type == _PDF_MIME or mime_type in _DOCX_MIMES

    def extract(self, data: bytes, mime_type: str) -> ExtractionResult:
        if mime_type == _PDF_MIME:
            elements = self._partition_pdf(data)
        elif mime_type in _DOCX_MIMES:
            elements = self._partition_docx(data)
        else:
            raise UnsupportedFileType(
                f"UnstructuredExtractor got unsupported MIME {mime_type!r}."
            )

        return _build_result(elements)

    def _partition_pdf(self, data: bytes) -> list[Any]:
        from unstructured.partition.pdf import partition_pdf

        logger.info(
            "unstructured.partition_pdf strategy=%s infer_tables=%s size=%dB",
            self._strategy,
            self._infer_table_structure,
            len(data),
        )
        return partition_pdf(
            file=io.BytesIO(data),
            strategy=self._strategy,
            infer_table_structure=self._infer_table_structure,
        )

    def _partition_docx(self, data: bytes) -> list[Any]:
        from unstructured.partition.docx import partition_docx

        logger.info("unstructured.partition_docx size=%dB", len(data))
        return partition_docx(file=io.BytesIO(data))


class ImageExtractor:
    """OCR path for raw images — unchanged from pre-F82.

    Unstructured has an image pipeline but Tesseract is already wired
    and works fine for the image formats we allow.
    """

    def __init__(self, vision: VisionProvider) -> None:
        self._vision = vision

    def supports(self, mime_type: str) -> bool:
        return mime_type in _IMAGE_MIMES

    def extract(self, data: bytes, mime_type: str) -> ExtractionResult:
        text = self._vision.extract_text_from_image(data)
        element = Element(
            kind="NarrativeText", text=text, page_number=1, order=0, metadata={}
        )
        return ExtractionResult(
            text=text, page_count=1, elements=[element] if text else []
        )


class CompositeExtractor:
    """Dispatch to the first extractor that supports the given MIME type.

    After F82.d, this is mostly a passthrough to ``UnstructuredExtractor``
    for PDFs and DOCX. ``ImageExtractor`` still handles raw images via
    the configured vision provider.
    """

    def __init__(
        self,
        *,
        strategy: str = "hi_res",
        infer_table_structure: bool = True,
        vision: VisionProvider | None = None,
    ) -> None:
        self._extractors = [
            UnstructuredExtractor(
                strategy=strategy,
                infer_table_structure=infer_table_structure,
            ),
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


def _build_result(raw_elements: list[Any]) -> ExtractionResult:
    """Convert unstructured's element objects to our ``Element`` dataclass.

    unstructured elements have: ``.text``, ``type(el).__name__`` for the
    kind, ``el.metadata.page_number``, and more structured metadata
    accessible via ``el.metadata.to_dict()``. We keep a subset that's
    useful downstream and drop layout coordinates (bbox) — too noisy
    for our uses today, can add later.
    """
    elements: list[Element] = []
    pages_seen: set[int] = set()
    text_parts: list[str] = []

    for order, raw in enumerate(raw_elements):
        kind = type(raw).__name__
        text = (raw.text or "").strip()
        if not text:
            continue

        page_number = None
        meta_dict: dict[str, Any] = {}
        if raw.metadata is not None:
            page_number = getattr(raw.metadata, "page_number", None)
            # Keep only pragmatic metadata; skip raw layout bboxes for now.
            raw_meta = (
                raw.metadata.to_dict() if hasattr(raw.metadata, "to_dict") else {}
            )
            for key in ("languages", "filetype", "text_as_html", "category_depth"):
                if key in raw_meta and raw_meta[key] is not None:
                    meta_dict[key] = raw_meta[key]

        if page_number is not None:
            pages_seen.add(page_number)

        # Tables: prefer the HTML/markdown representation if unstructured
        # provided one; else the plain text is the cell contents.
        if kind == "Table" and "text_as_html" in meta_dict:
            # Keep the HTML around as metadata; the chunker may convert
            # it to markdown. Plain text stays as the primary payload.
            pass

        elements.append(
            Element(
                kind=kind,
                text=text,
                page_number=page_number,
                order=order,
                metadata=meta_dict,
            )
        )
        text_parts.append(text)

    return ExtractionResult(
        text="\n\n".join(text_parts).strip(),
        page_count=max(pages_seen) if pages_seen else None,
        elements=elements,
    )
