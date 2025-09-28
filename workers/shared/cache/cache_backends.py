"""Cache Backend Implementations

This module provides abstract and concrete cache backend implementations:
- BaseCacheBackend: Abstract interface for cache backends
- RedisCacheBackend: Redis-based cache implementation
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from .redis_client import RedisClient

logger = logging.getLogger(__name__)


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

    @abstractmethod
    def mget(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from cache in a single operation.

        Args:
            keys: List of cache keys to retrieve

        Returns:
            Dict mapping keys to their values (only includes keys that exist)
        """
        pass

    @abstractmethod
    def mset(self, data: dict[str, tuple[dict[str, Any], int]]) -> int:
        """Set multiple values in cache with individual TTLs.

        Args:
            data: Dict mapping keys to (value, ttl) tuples

        Returns:
            Number of keys successfully set
        """
        pass

    @abstractmethod
    def keys(self, pattern: str) -> list[str]:
        """Get keys matching a pattern."""
        pass

    @abstractmethod
    def scan_keys(self, pattern: str, count: int = 100) -> list[str]:
        """Non-blocking scan for keys matching a pattern using SCAN cursor."""
        pass


class RedisCacheBackend(BaseCacheBackend):
    """Redis-based cache backend for workers."""

    def __init__(self, config=None):
        """Initialize Redis cache backend with configurable settings.

        Args:
            config: WorkerConfig instance or None to create default config
        """
        try:
            # Use provided config or create default one
            if config is None:
                from ..infrastructure.config import WorkerConfig

                config = WorkerConfig()

            # Get Redis cache configuration from WorkerConfig
            cache_config = config.get_cache_redis_config()

            if not cache_config.get("enabled", False):
                logger.info("Redis cache disabled in configuration")
                self.redis_client = None
                self.available = False
                return

            # Initialize RedisClient with cache configuration
            self.redis_client = RedisClient(
                host=cache_config["host"],
                port=cache_config["port"],
                username=cache_config.get("username"),
                password=cache_config.get("password"),
                db=cache_config["db"],
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )

            # Test connection
            if not self.redis_client.ping():
                raise ConnectionError("Failed to ping Redis server")

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

    def keys(self, pattern: str) -> list[str]:
        """Get keys matching pattern.

        ⚠️ WARNING: This method uses Redis KEYS command which can block the server!
        For production use, prefer scan_keys() which uses non-blocking SCAN.
        """
        if not self.available:
            return []

        try:
            # Log warning about blocking operation
            logger.warning(
                f"Using blocking KEYS command with pattern '{pattern}'. "
                "Consider using scan_keys() for production safety."
            )

            keys = self.redis_client.keys(pattern)
            # Convert bytes to strings if needed
            return [
                key.decode("utf-8") if isinstance(key, bytes) else key for key in keys
            ]
        except Exception as e:
            logger.error(f"Error getting keys for pattern {pattern}: {e}")
            return []

    def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern using non-blocking SCAN."""
        if not self.available:
            return 0

        try:
            # Use non-blocking SCAN instead of blocking KEYS
            keys = self.scan_keys(pattern)
            if keys:
                count = self.redis_client.delete(*keys)
                logger.debug(
                    f"Deleted {count} keys matching pattern {pattern} (using SCAN)"
                )
                return count
            return 0
        except Exception as e:
            logger.error(f"Error deleting pattern {pattern}: {e}")
            return 0

    def scan_keys(self, pattern: str, count: int = 100) -> list[str]:
        """Non-blocking scan for keys matching a pattern using SCAN cursor.

        This replaces the blocking KEYS command with SCAN for production safety.
        SCAN iterates through the keyspace in small chunks, preventing Redis blocking.

        Args:
            pattern: Redis pattern to match (e.g., "file_active:*")
            count: Hint for number of keys to return per SCAN iteration

        Returns:
            List of matching keys
        """
        if not self.available:
            return []

        try:
            keys = []
            cursor = 0

            # Use SCAN cursor to iterate through keyspace non-blocking
            while True:
                # SCAN returns (new_cursor, list_of_keys)
                cursor, batch_keys = self.redis_client.scan(
                    cursor=cursor, match=pattern, count=count
                )

                # Convert bytes to strings if needed and add to result
                batch_keys_str = [
                    key.decode("utf-8") if isinstance(key, bytes) else key
                    for key in batch_keys
                ]
                keys.extend(batch_keys_str)

                # cursor=0 means we've completed the full iteration
                if cursor == 0:
                    break

            logger.debug(f"SCAN found {len(keys)} keys matching pattern {pattern}")
            return keys

        except Exception as e:
            logger.error(f"Error scanning keys for pattern {pattern}: {e}")
            return []

    def mget(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from Redis cache in a single operation.

        Args:
            keys: List of cache keys to retrieve

        Returns:
            Dict mapping keys to their values (only includes keys that exist)
        """
        if not self.available or not keys:
            return {}

        try:
            # Use Redis mget for batch retrieval
            values = self.redis_client.mget(keys)
            result = {}

            for key, value_str in zip(keys, values, strict=False):
                if value_str:  # Skip None values (missing keys)
                    try:
                        data = json.loads(value_str)
                        if data:
                            # Check if cached data has timestamp and is still valid
                            if isinstance(data, dict) and "cached_at" in data:
                                result[key] = data
                            else:
                                # Backward compatibility for data without metadata
                                result[key] = {
                                    "data": data,
                                    "cached_at": datetime.now(UTC).isoformat(),
                                }
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in cache key {key}, skipping")

            logger.debug(f"Batch retrieved {len(result)}/{len(keys)} cache keys")
            return result

        except Exception as e:
            logger.error(f"Error batch getting cache keys: {e}")
            return {}

    def mset(self, data: dict[str, tuple[dict[str, Any], int]]) -> int:
        """Set multiple values in Redis cache with individual TTLs.

        Args:
            data: Dict mapping keys to (value, ttl) tuples

        Returns:
            Number of keys successfully set
        """
        if not self.available or not data:
            return 0

        try:
            # Use Redis pipeline for efficient batch operations
            pipe = self.redis_client.pipeline()
            successful_keys = 0

            for key, (value, ttl) in data.items():
                try:
                    # Add metadata to cached data
                    cache_data = {
                        "data": value,
                        "cached_at": datetime.now(UTC).isoformat(),
                        "ttl": ttl,
                    }

                    # Use pipeline to batch the setex operations
                    pipe.setex(key, ttl, json.dumps(cache_data))
                    successful_keys += 1

                except Exception as key_error:
                    logger.warning(f"Failed to prepare cache key {key}: {key_error}")

            # Execute all operations in the pipeline
            if successful_keys > 0:
                pipe.execute()
                logger.debug(f"Batch set {successful_keys} cache keys")

            return successful_keys

        except Exception as e:
            logger.error(f"Error batch setting cache keys: {e}")
            return 0
