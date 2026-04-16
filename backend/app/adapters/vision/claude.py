"""Claude vision provider — extracts text from images via the Anthropic API."""

from __future__ import annotations

import base64

import anthropic
from pydantic import SecretStr

_DEFAULT_PROMPT = (
    "Extract all text from this image. Preserve the original structure, "
    "headings, and formatting as closely as possible. "
    "Return only the extracted text, no commentary."
)


class ClaudeVisionProvider:
    def __init__(self, *, api_key: SecretStr, model: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key.get_secret_value())
        self._model = model

    def extract_text_from_image(
        self, image: bytes, *, prompt: str | None = None
    ) -> str:
        b64 = base64.standard_b64encode(image).decode("ascii")
        media_type = _guess_media_type(image)

        message = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt or _DEFAULT_PROMPT},
                    ],
                }
            ],
        )
        return message.content[0].text


def _guess_media_type(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    return "image/png"
