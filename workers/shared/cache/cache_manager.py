"""Cache Manager for API Client Operations

This module provides a high-level caching interface for managing API response data.
It handles cache operations with statistics tracking, TTL management, and automatic
serialization/deserialization of cached data.
"""

import logging
import time
from typing import Any

from .cache_backends import BaseCacheBackend, RedisCacheBackend
from .cache_utils import make_json_serializable, reconstruct_from_cache

logger = logging.getLogger(__name__)


class CacheManager:
    """Main caching interface for API client operations."""

    def __init__(self, backend: BaseCacheBackend | None = None, config=None):
        """Initialize cache manager.

        Args:
            backend: Cache backend to use. Defaults to RedisCacheBackend.
            config: WorkerConfig instance for configuration
        """
        from .cache_types import CacheConfig

        self.backend = backend or RedisCacheBackend(config)
        self.cache_config = CacheConfig
        self.stats = {"hits": 0, "misses": 0, "sets": 0, "deletes": 0, "errors": 0}

        if self.backend.available:
            logger.info("CacheManager initialized with Redis backend")
        else:
            logger.warning("CacheManager initialized with disabled backend")

    def get(self, key: str, operation_type: str = "default") -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key
            operation_type: Type of operation for TTL selection

        Returns:
            Cached data or None if not found
        """
        if not self.backend.available:
            return None

        try:
            start_time = time.time()
            cached_data = self.backend.get(key)

            if cached_data:
                self.stats["hits"] += 1
                response_time = (time.time() - start_time) * 1000
                logger.debug(
                    f"Cache HIT for {key} (type: {operation_type}) in {response_time:.1f}ms"
                )
                # Reconstruct objects from cached data with fallback handling
                raw_data = cached_data.get("data")
                try:
                    return reconstruct_from_cache(raw_data)
                except Exception as e:
                    # Cache reconstruction failed - invalidate corrupted entry and fallback to API
                    logger.warning(
                        f"Cache reconstruction failed for {key}: {e}. Invalidating cache entry."
                    )
                    self.stats["errors"] += 1
                    # Delete the corrupted cache entry
                    self.backend.delete(key)
                    # Return None to trigger cache miss behavior (fallback to API call)
                    return None
            else:
                self.stats["misses"] += 1
                response_time = (time.time() - start_time) * 1000
                logger.debug(
                    f"Cache MISS for {key} (type: {operation_type}) in {response_time:.1f}ms"
                )
                return None

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Error getting cache for {key}: {e}")
            return None

    def set(
        self, key: str, value: Any, operation_type: str = "custom", ttl: int | None = None
    ) -> bool:
        """Set value in cache.

        Args:
            key: Cache key
            value: Data to cache
            operation_type: Type of operation for TTL selection (CacheType enum or string)
            ttl: Override TTL in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.backend.available:
            return False

        try:
            from .cache_types import CacheConfig, CacheType

            # Convert string to enum if needed
            if isinstance(operation_type, str):
                try:
                    cache_type = CacheType(operation_type)
                except ValueError:
                    cache_type = CacheType.CUSTOM
            else:
                cache_type = operation_type

            # Convert value to JSON-serializable format before caching
            serializable_value = self._make_json_serializable(value)

            effective_ttl = ttl or CacheConfig.get_ttl(cache_type)
            success = self.backend.set(key, serializable_value, effective_ttl)

            if success:
                self.stats["sets"] += 1
                logger.debug(
                    f"Cached {key} (type: {cache_type.value}) with TTL {effective_ttl}s"
                )

            return success

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Error setting cache for {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if not self.backend.available:
            return False

        try:
            success = self.backend.delete(key)
            if success:
                self.stats["deletes"] += 1
            return success
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Error deleting cache key {key}: {e}")
            return False

    def invalidate_workflow(self, workflow_id: str):
        """Invalidate all cache entries related to a workflow."""
        from .cache_keys import CacheKeyGenerator

        keys_to_delete = [
            CacheKeyGenerator.workflow_key(workflow_id),
            CacheKeyGenerator.tool_instances_key(workflow_id),
            CacheKeyGenerator.workflow_endpoints_key(workflow_id),
        ]

        for key in keys_to_delete:
            self.delete(key)

        logger.info(f"Invalidated cache for workflow {workflow_id}")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = (
            (self.stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        )

        return {
            **self.stats,
            "hit_rate": f"{hit_rate:.1f}%",
            "total_requests": total_requests,
            "backend_available": self.backend.available,
        }

    def clear_stats(self):
        """Clear cache statistics."""
        self.stats = {key: 0 for key in self.stats}

    def _make_json_serializable(self, obj: Any) -> Any:
        """Convert an object to JSON-serializable format.

        Delegates to the common serialization utility.
        """
        return make_json_serializable(obj)
