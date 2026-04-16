"""Tesseract vision provider — offline OCR via pytesseract."""

from __future__ import annotations

import io


class TesseractVisionProvider:
    """Falls back to classical OCR. No API key, no network.

    Requires ``tesseract-ocr`` system package and the ``pytesseract`` +
    ``Pillow`` Python packages. Both are imported lazily so the rest of the
    app runs fine without them when another provider is selected.
    """

    def extract_text_from_image(
        self, image: bytes, *, prompt: str | None = None
    ) -> str:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(image))
        text: str = pytesseract.image_to_string(img)
        return text.strip()
