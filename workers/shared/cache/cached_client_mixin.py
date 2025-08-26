"""Cached API Client Mixin

This mixin provides caching capabilities for API client operations, designed to be
mixed into existing API client classes with minimal changes.
"""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from .base_cache import APIClientCache, CacheKeyGenerator
from .cache_utils import make_json_serializable

logger = logging.getLogger(__name__)


def cached_request(
    operation_type: str, cache_key_func: Callable | None = None, ttl: int | None = None
):
    """Decorator for caching API requests.

    Args:
        operation_type: Type of operation for TTL selection
        cache_key_func: Function to generate cache key from method arguments
        ttl: Override TTL in seconds
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Skip caching if cache is not available
            if not hasattr(self, "_cache") or not self._cache.backend.available:
                return func(self, *args, **kwargs)

            # Generate cache key
            if cache_key_func:
                cache_key = cache_key_func(self, *args, **kwargs)
            else:
                # Default key generation based on method name and first argument
                method_name = func.__name__
                first_arg = str(args[0]) if args else "no_args"
                cache_key = CacheKeyGenerator.custom_key(method_name, first_arg)

            # Try to get from cache first
            cached_result = self._cache.get(cache_key, operation_type)
            if cached_result is not None:
                logger.debug(f"Cache hit for {func.__name__} with key {cache_key}")
                return cached_result

            # Cache miss - call the actual method
            logger.debug(f"Cache miss for {func.__name__} with key {cache_key}")
            result = func(self, *args, **kwargs)

            # Cache successful results - convert to JSON-serializable format
            if result and hasattr(result, "success") and result.success:
                # Convert result to JSON-serializable format
                serializable_result = self._make_json_serializable(result)
                self._cache.set(cache_key, serializable_result, operation_type, ttl)
                logger.debug(f"Cached result for {func.__name__} with key {cache_key}")

            return result

        return wrapper

    return decorator


class CachedAPIClientMixin:
    """Mixin to add caching capabilities to API clients.

    This mixin provides:
    - Automatic cache initialization via _cache attribute
    - Cache statistics and management methods
    - Works seamlessly with @with_cache decorator

    The @with_cache decorator automatically detects and uses the _cache attribute.
    """

    def __init__(self, *args, **kwargs):
        """Initialize the cached client mixin."""
        super().__init__(*args, **kwargs)
        self._cache = APIClientCache()

        if self._cache.backend.available:
            logger.info(f"Caching enabled for {self.__class__.__name__}")
        else:
            logger.warning(
                f"Caching disabled for {self.__class__.__name__} - Redis not available"
            )

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics for this client."""
        return self._cache.get_stats()

    def clear_cache_stats(self):
        """Clear cache statistics."""
        self._cache.clear_stats()

    def invalidate_cache(self, pattern: str):
        """Invalidate cache entries matching pattern."""
        # This is a simple implementation - could be enhanced with pattern matching
        logger.info(f"Cache invalidation requested for pattern: {pattern}")

    # Cache management methods
    def invalidate_workflow_cache(self, workflow_id: str):
        """Invalidate all cache entries for a specific workflow."""
        if self._cache.backend.available:
            self._cache.invalidate_workflow(workflow_id)

    def invalidate_api_deployment_cache(
        self, api_deployment_id: str, organization_id: str
    ):
        """Invalidate cache for a specific API deployment."""
        if self._cache.backend.available:
            cache_key = CacheKeyGenerator.api_deployment_key(
                api_deployment_id, organization_id
            )
            self._cache.delete(cache_key)
            logger.info(f"Invalidated cache for API deployment {api_deployment_id}")

    def invalidate_pipeline_cache(self, pipeline_id: str):
        """Invalidate cache for a specific pipeline."""
        if self._cache.backend.available:
            cache_key = CacheKeyGenerator.pipeline_key(pipeline_id)
            self._cache.delete(cache_key)
            logger.info(f"Invalidated cache for pipeline {pipeline_id}")

    def _make_json_serializable(self, obj: Any) -> Any:
        """Convert an object to JSON-serializable format.

        Delegates to the common serialization utility.
        """
        return make_json_serializable(obj)
