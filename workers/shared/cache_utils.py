"""Redis Cache Utilities for Workers

Provides caching mechanisms to reduce database queries and improve performance.
Specifically optimized for callback pattern performance optimizations.
"""

import json
import logging
import time

import redis
from shared.config import WorkerConfig

logger = logging.getLogger(__name__)


class WorkerCacheManager:
    """Redis cache manager for worker performance optimization."""

    def __init__(self, config: WorkerConfig):
        """Initialize cache manager with worker configuration.

        Args:
            config: Worker configuration containing Redis settings
        """
        self.config = config
        self._redis_client = None
        self._last_connection_time = 0
        self._connection_id = None
        self._initialize_redis_client()

    def _initialize_redis_client(self):
        """Initialize Redis client from cache-specific configuration."""
        try:
            # Get cache-specific Redis configuration
            cache_config = self.config.get_cache_redis_config()

            if not cache_config.get("enabled"):
                logger.info("Redis cache disabled via configuration")
                return

            # Use direct cache Redis configuration (not Celery broker)
            redis_kwargs = {
                "host": cache_config["host"],
                "port": cache_config["port"],
                "db": cache_config["db"],
                "decode_responses": True,
                "socket_connect_timeout": 5,
                "socket_timeout": 5,
                "health_check_interval": 30,
            }

            # Add authentication if configured
            if cache_config.get("password"):
                redis_kwargs["password"] = cache_config["password"]
            if cache_config.get("username"):
                redis_kwargs["username"] = cache_config["username"]

            # Add SSL configuration if enabled
            if cache_config.get("ssl"):
                redis_kwargs["ssl"] = True
                redis_kwargs["ssl_cert_reqs"] = self.config.cache_redis_ssl_cert_reqs

            self._redis_client = redis.Redis(**redis_kwargs)

            # Test connection
            self._redis_client.ping()
            self._last_connection_time = time.time()
            # Create unique connection ID to detect reconnections
            self._connection_id = f"cache_conn_{int(self._last_connection_time)}"
            logger.info(
                f"Redis cache initialized: {cache_config['host']}:{cache_config['port']}/{cache_config['db']}"
            )

        except Exception as e:
            logger.warning(f"Failed to initialize Redis cache: {e}. Cache disabled.")
            self._redis_client = None
            self._connection_id = None

    @property
    def is_available(self) -> bool:
        """Check if Redis cache is available and detect reconnections."""
        if not self._redis_client:
            return False
        try:
            self._redis_client.ping()
            current_time = time.time()

            # Check if connection was lost and restored (potential stale data)
            if current_time - self._last_connection_time > 120:  # 2 minutes gap
                logger.warning(
                    "Redis connection gap detected, clearing potentially stale cache"
                )
                self._clear_all_cache()
                self._last_connection_time = current_time
                # Update connection ID to mark new session
                self._connection_id = f"cache_conn_{int(current_time)}"

            return True
        except Exception:
            return False

    def _clear_all_cache(self):
        """Clear all cache data to prevent stale data after reconnection."""
        if not self._redis_client:
            return

        try:
            # Find all cache keys with our patterns
            patterns = [
                "exec_status:*",
                "pipeline_status:*",
                "batch_summary:*",
                "callback_attempts:*",
                "backoff_attempts:*",
                "circuit_breaker:*",
            ]

            keys_to_delete = []
            for pattern in patterns:
                keys = self._redis_client.keys(pattern)
                keys_to_delete.extend(keys)

            if keys_to_delete:
                self._redis_client.delete(*keys_to_delete)
                logger.info(f"Cleared {len(keys_to_delete)} potentially stale cache keys")

        except Exception as e:
            logger.warning(f"Failed to clear cache after reconnection: {e}")

    def _is_cache_data_valid(self, cache_data: dict) -> bool:
        """Validate cache data to detect staleness after reconnection.

        Args:
            cache_data: Cached data dictionary

        Returns:
            True if cache data is valid and not stale
        """
        if not isinstance(cache_data, dict):
            return False

        # Check if data has connection ID (new feature)
        data_connection_id = cache_data.get("connection_id")
        if data_connection_id and data_connection_id != self._connection_id:
            logger.debug("Cache data from previous connection, treating as stale")
            return False

        # Check timestamp-based expiration
        cached_at = cache_data.get("cached_at", 0)
        if time.time() - cached_at > 300:  # 5 minutes absolute max
            logger.debug("Cache data too old, treating as stale")
            return False

        return True

    def get_execution_status(
        self, execution_id: str, organization_id: str
    ) -> dict | None:
        """Get cached execution status.

        Args:
            execution_id: Execution ID
            organization_id: Organization context

        Returns:
            Cached status data or None if not found/expired
        """
        if not self.is_available:
            return None

        try:
            cache_key = f"exec_status:{organization_id}:{execution_id}"
            cached_data = self._redis_client.get(cache_key)

            if cached_data:
                data = json.loads(cached_data)

                # Validate cache data for staleness
                if self._is_cache_data_valid(data):
                    # Check if cache is fresh (within 30 seconds)
                    if time.time() - data.get("cached_at", 0) < 30:
                        logger.debug(f"Cache hit for execution {execution_id}")
                        return data.get("status_data")

                # Remove expired or stale cache
                self._redis_client.delete(cache_key)
                logger.debug(f"Removed stale/expired cache for execution {execution_id}")

        except Exception as e:
            logger.warning(f"Cache get error for execution {execution_id}: {e}")

        return None

    def set_execution_status(
        self, execution_id: str, organization_id: str, status_data: dict, ttl: int = 60
    ):
        """Cache execution status data.

        Args:
            execution_id: Execution ID
            organization_id: Organization context
            status_data: Status data to cache
            ttl: Time-to-live in seconds
        """
        if not self.is_available:
            return

        try:
            cache_key = f"exec_status:{organization_id}:{execution_id}"
            cache_data = {
                "status_data": status_data,
                "cached_at": time.time(),
                "connection_id": self._connection_id,  # Track which connection created this cache
            }

            self._redis_client.setex(cache_key, ttl, json.dumps(cache_data))
            logger.debug(f"Cached execution status for {execution_id}")

        except Exception as e:
            logger.warning(f"Cache set error for execution {execution_id}: {e}")

    def invalidate_execution_status(self, execution_id: str, organization_id: str):
        """Invalidate cached execution status.

        Args:
            execution_id: Execution ID
            organization_id: Organization context
        """
        if not self.is_available:
            return

        try:
            cache_key = f"exec_status:{organization_id}:{execution_id}"
            self._redis_client.delete(cache_key)
            logger.debug(f"Invalidated cache for execution {execution_id}")

        except Exception as e:
            logger.warning(f"Cache invalidation error for execution {execution_id}: {e}")

    def get_pipeline_status(self, pipeline_id: str, organization_id: str) -> dict | None:
        """Get cached pipeline status.

        Args:
            pipeline_id: Pipeline ID
            organization_id: Organization context

        Returns:
            Cached pipeline data or None if not found/expired
        """
        if not self.is_available:
            return None

        try:
            cache_key = f"pipeline_status:{organization_id}:{pipeline_id}"
            cached_data = self._redis_client.get(cache_key)

            if cached_data:
                data = json.loads(cached_data)

                # Validate cache data for staleness
                if self._is_cache_data_valid(data):
                    # Check if cache is fresh (within 60 seconds for pipelines)
                    if time.time() - data.get("cached_at", 0) < 60:
                        logger.debug(f"Cache hit for pipeline {pipeline_id}")
                        return data.get("pipeline_data")

                # Remove expired or stale cache
                self._redis_client.delete(cache_key)
                logger.debug(f"Removed stale/expired cache for pipeline {pipeline_id}")

        except Exception as e:
            logger.warning(f"Cache get error for pipeline {pipeline_id}: {e}")

        return None

    def set_pipeline_status(
        self, pipeline_id: str, organization_id: str, pipeline_data: dict, ttl: int = 120
    ):
        """Cache pipeline status data.

        Args:
            pipeline_id: Pipeline ID
            organization_id: Organization context
            pipeline_data: Pipeline data to cache
            ttl: Time-to-live in seconds
        """
        if not self.is_available:
            return

        try:
            cache_key = f"pipeline_status:{organization_id}:{pipeline_id}"
            cache_data = {
                "pipeline_data": pipeline_data,
                "cached_at": time.time(),
                "connection_id": self._connection_id,  # Track which connection created this cache
            }

            self._redis_client.setex(cache_key, ttl, json.dumps(cache_data))
            logger.debug(f"Cached pipeline status for {pipeline_id}")

        except Exception as e:
            logger.warning(f"Cache set error for pipeline {pipeline_id}: {e}")

    def invalidate_pipeline_status(self, pipeline_id: str, organization_id: str):
        """Invalidate cached pipeline status.

        Args:
            pipeline_id: Pipeline ID
            organization_id: Organization context
        """
        if not self.is_available:
            return

        try:
            cache_key = f"pipeline_status:{organization_id}:{pipeline_id}"
            self._redis_client.delete(cache_key)
            logger.debug(f"Invalidated pipeline cache for {pipeline_id}")

        except Exception as e:
            logger.warning(f"Cache invalidation error for pipeline {pipeline_id}: {e}")

    def get_batch_status_summary(
        self, execution_id: str, organization_id: str
    ) -> dict | None:
        """Get cached batch processing summary.

        Args:
            execution_id: Execution ID
            organization_id: Organization context

        Returns:
            Cached batch summary or None if not found/expired
        """
        if not self.is_available:
            return None

        try:
            cache_key = f"batch_summary:{organization_id}:{execution_id}"
            cached_data = self._redis_client.get(cache_key)

            if cached_data:
                data = json.loads(cached_data)

                # Validate cache data for staleness
                if self._is_cache_data_valid(data):
                    # Batch summaries are fresh for 45 seconds
                    if time.time() - data.get("cached_at", 0) < 45:
                        logger.debug(f"Cache hit for batch summary {execution_id}")
                        return data.get("summary_data")

                # Remove expired or stale cache
                self._redis_client.delete(cache_key)
                logger.debug(
                    f"Removed stale/expired cache for batch summary {execution_id}"
                )

        except Exception as e:
            logger.warning(f"Cache get error for batch summary {execution_id}: {e}")

        return None

    def set_batch_status_summary(
        self, execution_id: str, organization_id: str, summary_data: dict, ttl: int = 90
    ):
        """Cache batch processing summary.

        Args:
            execution_id: Execution ID
            organization_id: Organization context
            summary_data: Batch summary data to cache
            ttl: Time-to-live in seconds
        """
        if not self.is_available:
            return

        try:
            cache_key = f"batch_summary:{organization_id}:{execution_id}"
            cache_data = {
                "summary_data": summary_data,
                "cached_at": time.time(),
                "connection_id": self._connection_id,  # Track which connection created this cache
            }

            self._redis_client.setex(cache_key, ttl, json.dumps(cache_data))
            logger.debug(f"Cached batch summary for {execution_id}")

        except Exception as e:
            logger.warning(f"Cache set error for batch summary {execution_id}: {e}")

    def increment_callback_attempt(self, execution_id: str, organization_id: str) -> int:
        """Increment and get callback attempt counter.

        Args:
            execution_id: Execution ID
            organization_id: Organization context

        Returns:
            Current attempt count
        """
        if not self.is_available:
            return 1

        try:
            cache_key = f"callback_attempts:{organization_id}:{execution_id}"
            current_attempts = self._redis_client.incr(cache_key)

            # Set expiration on first increment
            if current_attempts == 1:
                self._redis_client.expire(cache_key, 3600)  # Expire after 1 hour

            return current_attempts

        except Exception as e:
            logger.warning(
                f"Failed to increment callback attempts for {execution_id}: {e}"
            )
            return 1

    def get_callback_backoff_delay(
        self, execution_id: str, organization_id: str
    ) -> float:
        """Calculate exponential backoff delay for callback retries.

        Args:
            execution_id: Execution ID
            organization_id: Organization context

        Returns:
            Delay in seconds (exponential backoff)
        """
        attempt_count = self.increment_callback_attempt(execution_id, organization_id)

        # Exponential backoff: 2^attempt seconds, max 300 seconds (5 minutes)
        base_delay = 2.0
        max_delay = 300.0

        delay = min(base_delay ** min(attempt_count, 8), max_delay)

        logger.debug(
            f"Callback attempt {attempt_count} for {execution_id}, delay: {delay}s"
        )
        return delay

    def clear_callback_attempts(self, execution_id: str, organization_id: str):
        """Clear callback attempt counter after successful completion.

        Args:
            execution_id: Execution ID
            organization_id: Organization context
        """
        if not self.is_available:
            return

        try:
            cache_key = f"callback_attempts:{organization_id}:{execution_id}"
            self._redis_client.delete(cache_key)
            logger.debug(f"Cleared callback attempts for {execution_id}")

        except Exception as e:
            logger.warning(f"Failed to clear callback attempts for {execution_id}: {e}")

    def batch_invalidate_execution_cache(
        self, execution_ids: list[str], organization_id: str
    ):
        """Batch invalidate multiple execution caches.

        Args:
            execution_ids: List of execution IDs
            organization_id: Organization context
        """
        if not self.is_available or not execution_ids:
            return

        try:
            # Build cache keys
            cache_keys = []
            for execution_id in execution_ids:
                cache_keys.extend(
                    [
                        f"exec_status:{organization_id}:{execution_id}",
                        f"batch_summary:{organization_id}:{execution_id}",
                        f"callback_attempts:{organization_id}:{execution_id}",
                    ]
                )

            # Delete in batches
            if cache_keys:
                self._redis_client.delete(*cache_keys)
                logger.debug(
                    f"Batch invalidated cache for {len(execution_ids)} executions"
                )

        except Exception as e:
            logger.warning(f"Batch cache invalidation error: {e}")

    def get_cache_stats(self) -> dict:
        """Get cache performance statistics.

        Returns:
            Dictionary with cache statistics
        """
        if not self.is_available:
            return {"status": "unavailable", "reason": "redis_not_connected"}

        try:
            info = self._redis_client.info()

            return {
                "status": "available",
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory_human", "unknown"),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": round(
                    info.get("keyspace_hits", 0)
                    / max(
                        info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1
                    )
                    * 100,
                    2,
                ),
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}


class CacheDecorator:
    """Decorator for caching API responses to reduce database queries."""

    def __init__(self, cache_manager: WorkerCacheManager, ttl: int = 60):
        """Initialize cache decorator.

        Args:
            cache_manager: Cache manager instance
            ttl: Time-to-live in seconds
        """
        self.cache_manager = cache_manager
        self.ttl = ttl

    def __call__(self, func):
        """Wrap function with caching logic."""

        def wrapper(*args, **kwargs):
            # Extract cache key from function arguments
            # This is a simple implementation - can be enhanced for specific use cases
            if not self.cache_manager.is_available:
                return func(*args, **kwargs)

            # For now, just call the function (can be enhanced with specific caching logic)
            return func(*args, **kwargs)

        return wrapper


# Global cache manager instance (initialized per worker)
_cache_manager = None


def get_cache_manager() -> WorkerCacheManager | None:
    """Get global cache manager instance.

    Returns:
        Cache manager instance or None if not initialized
    """
    return _cache_manager


def initialize_cache_manager(config: WorkerConfig) -> WorkerCacheManager:
    """Initialize global cache manager.

    Args:
        config: Worker configuration

    Returns:
        Initialized cache manager
    """
    global _cache_manager
    _cache_manager = WorkerCacheManager(config)
    return _cache_manager
