"""API Client Caching Framework

This package provides caching functionality for API client operations to reduce
internal API calls and improve performance for relatively static data.
"""

from .cache_backends import BaseCacheBackend, RedisCacheBackend
from .cache_decorator import with_cache
from .cache_keys import CacheKeyGenerator
from .cache_manager import CacheManager
from .cached_client_mixin import CachedAPIClientMixin

# Backward compatibility alias
APIClientCache = CacheManager

__all__ = [
    "CacheManager",
    "APIClientCache",
    "BaseCacheBackend",
    "RedisCacheBackend",
    "CacheKeyGenerator",
    "CachedAPIClientMixin",
    "with_cache",
]
