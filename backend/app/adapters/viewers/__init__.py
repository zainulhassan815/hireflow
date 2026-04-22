"""Document viewer providers.

Factory-pattern analogue to `llm`, `embeddings`, and `vision` adapters:
each provider handles one source format, picks a canonical kind, and
returns a `ViewablePayload` the frontend can render. Adding a new
format = one provider file + one registry line. See
``docs/features.md`` → F105 and ``docs/dev/F105a-viewer-protocol/``.
"""

from app.adapters.viewers.fallback import FallbackProvider
from app.adapters.viewers.passthrough import (
    PassthroughImageProvider,
    PassthroughPdfProvider,
)
from app.adapters.viewers.protocol import (
    ViewableKind,
    ViewablePayload,
    ViewerProvider,
)
from app.adapters.viewers.registry import ViewerRegistry, build_default_registry

__all__ = [
    "FallbackProvider",
    "PassthroughImageProvider",
    "PassthroughPdfProvider",
    "ViewableKind",
    "ViewablePayload",
    "ViewerProvider",
    "ViewerRegistry",
    "build_default_registry",
]
