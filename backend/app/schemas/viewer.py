"""Viewer response DTOs (F105)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ViewablePayloadResponse(BaseModel):
    """Everything the frontend needs to render one document.

    The client switches on ``kind`` and reaches for whichever of
    ``url`` / ``data`` applies. ``meta`` carries render hints
    (page counts, sheet names, reason strings for
    ``kind=unsupported``) and is intentionally loose — adding a
    hint later doesn't break existing clients.
    """

    kind: Literal["pdf", "image", "table", "text", "unsupported"] = Field(
        ...,
        description=(
            "Canonical render kind. ``pdf`` / ``image`` → use ``url``. "
            "``table`` / ``text`` → use ``data`` (inline JSON). "
            "``unsupported`` → show a download affordance; no inline "
            "render is available."
        ),
        examples=["pdf"],
    )
    url: str | None = Field(
        None,
        description=(
            "Time-limited signed URL the browser can GET directly. "
            "Populated for ``pdf`` / ``image`` kinds only."
        ),
        examples=["https://minio.local/bucket/owner-id/doc-id/file.pdf?X-Amz-..."],
    )
    data: dict | None = Field(
        None,
        description=(
            "Inline payload for kinds that ship their content in the "
            "response body (``table`` / ``text``). Shape is kind-"
            "specific; see F105.c / F105.d."
        ),
    )
    meta: dict = Field(
        default_factory=dict,
        description=(
            "Optional render hints: ``size_bytes``, ``mime_type``, "
            "``reason`` (for ``unsupported``), and future additions "
            "like page counts or sheet names."
        ),
        examples=[{"size_bytes": 123456, "mime_type": "application/pdf"}],
    )
