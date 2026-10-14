"""Process-wide provider registry.

OSS registers its providers from ``GlobalSearchConfig.ready()``; cloud apps
register theirs from their own ``ready()``, so a type exists exactly where
its app is installed and OSS never names a cloud type.
"""

from __future__ import annotations

import logging

from global_search.providers import SearchProvider

logger = logging.getLogger(__name__)

_providers: dict[str, SearchProvider] = {}


def register_provider(provider: SearchProvider) -> None:
    """Register ``provider`` under its ``type_key``.

    Re-registering the same class is a no-op, so a repeated ``ready()`` is
    harmless; a different class claiming a taken key is a wiring bug.
    """
    existing = _providers.get(provider.type_key)
    if existing is not None:
        if type(existing) is type(provider):
            return
        raise ValueError(
            f"Search type '{provider.type_key}' is already registered by "
            f"{type(existing).__name__}"
        )
    _providers[provider.type_key] = provider
    logger.debug("Registered global search provider '%s'", provider.type_key)


def unregister_provider(type_key: str) -> None:
    _providers.pop(type_key, None)


def get_providers() -> list[SearchProvider]:
    """Registered providers in rail order."""
    return sorted(_providers.values(), key=lambda p: (p.order, p.type_key))
