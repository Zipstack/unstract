"""Cache decorator for API client methods.

This module provides a clean decorator-based approach for caching API responses
without repetitive checks or hasattr calls.
"""

import functools
import logging
from collections.abc import Callable
from typing import Union

from .base_cache import CacheKeyGenerator
from .cache_types import CacheType

logger = logging.getLogger(__name__)


def with_cache(
    cache_type: Union[str, "CacheType"],
    key_extractor: Callable | None = None,
    ttl: int | None = None,
):
    """Decorator to add caching to API client methods.

    This decorator:
    - Automatically checks if caching is available
    - Handles cache hits/misses
    - Caches successful results
    - Falls back gracefully when cache is unavailable

    Args:
        cache_type: Type of cache operation (CacheType enum or string)
        key_extractor: Optional function to extract cache key from arguments
        ttl: Optional TTL override in seconds

    Example:
        @with_cache(CacheType.WORKFLOW, lambda self, wf_id, org_id: str(wf_id))
        def get_workflow_definition(self, workflow_id, organization_id=None):
            # Method implementation
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Try to use cache if available (no hasattr needed)
            try:
                if getattr(self, "_cache", None) and self._cache.backend.available:
                    # Generate cache key
                    if key_extractor:
                        cache_key_suffix = key_extractor(self, *args, **kwargs)
                    else:
                        # Default: use first argument as key
                        cache_key_suffix = str(args[0]) if args else "default"

                    # Convert enum to string value if needed
                    from .cache_types import CacheType

                    cache_type_str = (
                        cache_type.value
                        if hasattr(cache_type, "value")
                        else str(cache_type)
                    )

                    # Build full cache key based on cache type
                    if cache_type_str == CacheType.WORKFLOW.value:
                        cache_key = CacheKeyGenerator.workflow_key(cache_key_suffix)
                    elif cache_type_str == CacheType.API_DEPLOYMENT.value:
                        # Need org_id for API deployment
                        org_id = kwargs.get("organization_id") or getattr(
                            self, "organization_id", None
                        )
                        if org_id:
                            cache_key = CacheKeyGenerator.api_deployment_key(
                                cache_key_suffix, org_id
                            )
                        else:
                            cache_key = None
                    elif cache_type_str == CacheType.TOOL_INSTANCES.value:
                        cache_key = CacheKeyGenerator.tool_instances_key(cache_key_suffix)
                    elif cache_type_str == CacheType.WORKFLOW_ENDPOINTS.value:
                        cache_key = CacheKeyGenerator.workflow_endpoints_key(
                            cache_key_suffix
                        )
                    else:
                        cache_key = CacheKeyGenerator.custom_key(
                            cache_type_str, cache_key_suffix
                        )

                    # Check cache if we have a valid key
                    if cache_key:
                        cached_result = self._cache.get(cache_key, cache_type_str)
                        if cached_result is not None:
                            logger.debug(
                                f"Cache HIT for {func.__name__} (key: {cache_key})"
                            )
                            return cached_result
                        logger.debug(f"Cache MISS for {func.__name__} (key: {cache_key})")

                    # Call original method
                    result = func(self, *args, **kwargs)

                    # Cache successful results
                    if cache_key and result:
                        # Check if result indicates success
                        is_successful = (
                            (hasattr(result, "success") and result.success)
                            or (isinstance(result, dict) and result.get("success"))
                            or (
                                not hasattr(result, "success")
                            )  # Assume success if no success attribute
                        )

                        if is_successful:
                            self._cache.set(cache_key, result, cache_type_str, ttl)
                            logger.debug(
                                f"Cached result for {func.__name__} (key: {cache_key})"
                            )

                    return result
                else:
                    # No cache available, just call the method
                    return func(self, *args, **kwargs)

            except Exception as e:
                # If anything goes wrong with caching, just call the original method
                logger.debug(
                    f"Cache error in {func.__name__}: {e}, falling back to direct call"
                )
                return func(self, *args, **kwargs)

        return wrapper

    return decorator


def cache_key_from_first_arg(self, *args, **kwargs) -> str:
    """Extract cache key from first argument."""
    return str(args[0]) if args else "default"


def cache_key_from_workflow_id(self, workflow_id, *args, **kwargs) -> str:
    """Extract cache key from workflow_id parameter."""
    return str(workflow_id)


def cache_key_from_api_id(self, api_id, *args, **kwargs) -> str:
    """Extract cache key from api_id parameter."""
    return str(api_id)
