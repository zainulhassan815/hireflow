"""Ordered registry of ViewerProviders.

Providers are tried in list order; first ``accepts()`` wins. The
fallback goes last — its ``accepts()`` always returns True, so any
provider placed after it becomes unreachable.
"""

from __future__ import annotations

from app.adapters.viewers.fallback import FallbackProvider
from app.adapters.viewers.office import OfficeToPdfProvider
from app.adapters.viewers.passthrough import (
    PassthroughImageProvider,
    PassthroughPdfProvider,
)
from app.adapters.viewers.protocol import ViewerProvider


class ViewerRegistry:
    def __init__(self, providers: list[ViewerProvider]) -> None:
        self._providers = list(providers)

    def for_mime(self, mime_type: str | None) -> ViewerProvider:
        for provider in self._providers:
            if provider.accepts(mime_type):
                return provider
        # Unreachable when a FallbackProvider is registered, but we
        # raise rather than return None so a misconfigured registry
        # surfaces loudly instead of 500ing deep in a handler.
        raise LookupError(
            f"no ViewerProvider accepts mime={mime_type!r}; "
            "registry is missing a fallback"
        )


def build_default_registry() -> ViewerRegistry:
    """Default provider order for F105.a.

    PDF and image are checked before fallback. F105.b/c/d will insert
    more concrete providers above the fallback; each lands as one
    line here plus one file in ``app/adapters/viewers/``.
    """
    return ViewerRegistry(
        [
            PassthroughPdfProvider(),
            PassthroughImageProvider(),
            OfficeToPdfProvider(),
            # Must stay last — accepts() is unconditional.
            FallbackProvider(),
        ]
    )
