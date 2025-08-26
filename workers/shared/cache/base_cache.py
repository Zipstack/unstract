"""Base Caching Framework for API Client Operations

This module provides a flexible caching layer for API client operations with:
- Redis-based storage
- Configurable TTL per operation type
- Key generation strategies
- Cache invalidation patterns
- Expandable for different cache backends
"""

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from .cache_utils import make_json_serializable, reconstruct_from_cache

logger = logging.getLogger(__name__)


class CacheKeyGenerator:
    """Generates consistent cache keys for API operations."""

    @staticmethod
    def workflow_key(workflow_id: str) -> str:
        """Generate cache key for workflow data."""
        return f"worker_cache:workflow:{workflow_id}"

    @staticmethod
    def pipeline_key(pipeline_id: str) -> str:
        """Generate cache key for pipeline data."""
        return f"worker_cache:pipeline:{pipeline_id}"

    @staticmethod
    def api_deployment_key(api_id: str, org_id: str) -> str:
        """Generate cache key for API deployment data."""
        return f"worker_cache:api_deployment:{org_id}:{api_id}"

    @staticmethod
    def tool_instances_key(workflow_id: str) -> str:
        """Generate cache key for tool instances."""
        return f"worker_cache:tool_instances:{workflow_id}"

    @staticmethod
    def workflow_endpoints_key(workflow_id: str) -> str:
        """Generate cache key for workflow endpoints."""
        return f"worker_cache:workflow_endpoints:{workflow_id}"

    @staticmethod
    def custom_key(operation: str, *args: str) -> str:
        """Generate cache key for custom operations."""
        # Create a hash of the arguments for consistent keys
        args_hash = hashlib.md5(":".join(args).encode()).hexdigest()[:8]
        return f"worker_cache:{operation}:{args_hash}"


class BaseCacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    def get(self, key: str) -> dict[str, Any] | None:
        """Get value from cache."""
        pass

    @abstractmethod
    def set(self, key: str, value: dict[str, Any], ttl: int) -> bool:
        """Set value in cache with TTL."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        pass

    @abstractmethod
    def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern."""
        pass


class RedisCacheBackend(BaseCacheBackend):
    """Redis-based cache backend for workers."""

    def __init__(self, config=None):
        """Initialize Redis cache backend with configurable settings.

        Args:
            config: WorkerConfig instance or None to create default config
        """
        try:
            import redis

            # Use provided config or create default one
            if config is None:
                from ..config import WorkerConfig

                config = WorkerConfig()

            # Get Redis cache configuration from WorkerConfig
            cache_config = config.get_cache_redis_config()

            if not cache_config.get("enabled", False):
                logger.info("Redis cache disabled in configuration")
                self.redis_client = None
                self.available = False
                return

            # Create Redis connection config
            redis_config = {
                "host": cache_config["host"],
                "port": cache_config["port"],
                "db": cache_config["db"],
                "decode_responses": True,
                "socket_timeout": 5,
                "socket_connect_timeout": 5,
                "health_check_interval": 30,
            }

            # Add authentication if provided
            if cache_config.get("password"):
                redis_config["password"] = cache_config["password"]
            if cache_config.get("username"):
                redis_config["username"] = cache_config["username"]

            # Add SSL configuration if enabled
            if cache_config.get("ssl", False):
                redis_config["ssl"] = True
                if cache_config.get("ssl_cert_reqs"):
                    redis_config["ssl_cert_reqs"] = cache_config["ssl_cert_reqs"]

            # Initialize Redis client
            self.redis_client = redis.Redis(**redis_config)

            # Test connection
            self.redis_client.ping()

            self.available = True
            logger.info(
                f"RedisCacheBackend initialized successfully: {cache_config['host']}:{cache_config['port']}/{cache_config['db']}"
            )

        except ImportError:
            logger.error("Redis module not available - install with: pip install redis")
            self.redis_client = None
            self.available = False
        except Exception as e:
            logger.warning(f"Failed to initialize RedisCacheBackend: {e}")
            self.redis_client = None
            self.available = False

    def get(self, key: str) -> dict[str, Any] | None:
        """Get value from Redis cache."""
        if not self.available:
            return None

        try:
            data_str = self.redis_client.get(key)
            data = json.loads(data_str) if data_str else None

            if data:
                # Check if cached data has timestamp and is still valid
                if isinstance(data, dict) and "cached_at" in data:
                    return data
                # Backward compatibility for data without metadata
                return {"data": data, "cached_at": datetime.now(UTC).isoformat()}
            return None
        except Exception as e:
            logger.error(f"Error getting cache key {key}: {e}")
            return None

    def set(self, key: str, value: dict[str, Any], ttl: int) -> bool:
        """Set value in Redis cache with TTL."""
        if not self.available:
            return False

        try:
            # Add metadata to cached data
            cache_data = {
                "data": value,
                "cached_at": datetime.now(UTC).isoformat(),
                "ttl": ttl,
            }

            self.redis_client.setex(key, ttl, json.dumps(cache_data))
            logger.debug(f"Cached key {key} with TTL {ttl}s")
            return True
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete key from Redis cache."""
        if not self.available:
            return False

        try:
            deleted_count = self.redis_client.delete(key)
            logger.debug(f"Deleted cache key {key} (count: {deleted_count})")
            return deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern."""
        if not self.available:
            return 0

        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                count = self.redis_client.delete(*keys)
                logger.debug(f"Deleted {count} keys matching pattern {pattern}")
                return count
            return 0
        except Exception as e:
            logger.error(f"Error deleting pattern {pattern}: {e}")
            return 0


class APIClientCache:
    """Main caching interface for API client operations."""

    def __init__(self, backend: BaseCacheBackend | None = None, config=None):
        """Initialize API client cache.

        Args:
            backend: Cache backend to use. Defaults to RedisCacheBackend.
            config: WorkerConfig instance for configuration
        """
        from .cache_types import CacheConfig

        self.backend = backend or RedisCacheBackend(config)
        self.cache_config = CacheConfig
        self.stats = {"hits": 0, "misses": 0, "sets": 0, "deletes": 0, "errors": 0}

        if self.backend.available:
            logger.info("APIClientCache initialized with Redis backend")
        else:
            logger.warning("APIClientCache initialized with disabled backend")

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
                # Reconstruct objects from cached data
                raw_data = cached_data.get("data")
                return reconstruct_from_cache(raw_data)
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
