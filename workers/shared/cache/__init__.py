"""API Client Caching Framework

This package provides caching functionality for API client operations to reduce
internal API calls and improve performance for relatively static data.
"""

from .base_cache import (
    APIClientCache,
    BaseCacheBackend,
    CacheKeyGenerator,
    RedisCacheBackend,
)
from .cache_decorator import with_cache
from .cached_client_mixin import CachedAPIClientMixin

__all__ = [
    "APIClientCache",
    "BaseCacheBackend",
    "RedisCacheBackend",
    "CacheKeyGenerator",
    "CachedAPIClientMixin",
    "with_cache",
]
