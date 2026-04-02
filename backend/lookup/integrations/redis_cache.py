"""Redis cache implementation for Look-Up LLM responses.

This module provides a Redis-based cache for storing and retrieving
LLM responses to improve performance and reduce API costs.
"""

import hashlib
import logging
import time
from typing import Any

try:
    import redis
    from redis.exceptions import RedisError

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from django.conf import settings

logger = logging.getLogger(__name__)


class RedisLLMCache:
    """Redis-based cache for LLM responses.

    Provides persistent caching with TTL support and
    automatic failover to in-memory cache if Redis is unavailable.
    """

    def __init__(
        self,
        ttl_hours: int = 24,
        key_prefix: str = "lookup:llm:",
        fallback_to_memory: bool = True,
    ):
        """Initialize Redis cache.

        Args:
            ttl_hours: Time-to-live for cache entries in hours
            key_prefix: Prefix for all cache keys
            fallback_to_memory: Use in-memory cache if Redis unavailable
        """
        self.ttl_seconds = ttl_hours * 3600
        self.key_prefix = key_prefix
        self.fallback_to_memory = fallback_to_memory

        # Initialize Redis connection
        self.redis_client = self._init_redis()

        # Fallback in-memory cache
        if self.fallback_to_memory:
            from ..services.llm_cache import LLMResponseCache

            self.memory_cache = LLMResponseCache(ttl_hours)
        else:
            self.memory_cache = None

    def _init_redis(self) -> Any | None:
        """Initialize Redis connection.

        Returns:
            Redis client or None if unavailable
        """
        if not REDIS_AVAILABLE:
            logger.warning("Redis package not installed, using fallback cache")
            return None

        try:
            # Get Redis configuration from settings
            redis_host = getattr(settings, "REDIS_HOST", "localhost")
            redis_port = getattr(settings, "REDIS_PORT", 6379)
            redis_db = getattr(settings, "REDIS_CACHE_DB", 1)
            redis_password = getattr(settings, "REDIS_PASSWORD", None)

            # Create Redis client
            client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )

            # Test connection
            client.ping()
            logger.info(f"Connected to Redis at {redis_host}:{redis_port}/{redis_db}")
            return client

        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            return None

    def generate_cache_key(self, prompt: str, reference_data: str) -> str:
        """Generate a cache key from prompt and reference data.

        Args:
            prompt: The resolved prompt
            reference_data: The reference data content

        Returns:
            SHA256 hash as cache key
        """
        combined = f"{prompt}{reference_data}"
        hash_obj = hashlib.sha256(combined.encode("utf-8"))
        return f"{self.key_prefix}{hash_obj.hexdigest()}"

    def get(self, key: str) -> str | None:
        """Get cached response.

        Args:
            key: Cache key

        Returns:
            Cached response or None if not found/expired
        """
        # Try Redis first
        if self.redis_client:
            try:
                value = self.redis_client.get(key)
                if value:
                    logger.debug(f"Redis cache hit for key: {key[:20]}...")
                    self._update_stats("hits")
                    return value
                else:
                    logger.debug(f"Redis cache miss for key: {key[:20]}...")
                    self._update_stats("misses")
            except RedisError as e:
                logger.error(f"Redis get error: {e}")
                # Fall through to memory cache

        # Fallback to memory cache
        if self.memory_cache:
            # Remove prefix for memory cache
            memory_key = key.replace(self.key_prefix, "")
            value = self.memory_cache.get(memory_key)
            if value:
                logger.debug(f"Memory cache hit for key: {key[:20]}...")
            return value

        return None

    def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        """Set cache value.

        Args:
            key: Cache key
            value: Response to cache
            ttl: Optional TTL override in seconds

        Returns:
            True if successful
        """
        ttl = ttl or self.ttl_seconds

        # Try Redis first
        if self.redis_client:
            try:
                self.redis_client.setex(name=key, time=ttl, value=value)
                logger.debug(f"Cached to Redis with key: {key[:20]}... (TTL: {ttl}s)")
                self._update_stats("sets")
                return True
            except RedisError as e:
                logger.error(f"Redis set error: {e}")
                # Fall through to memory cache

        # Fallback to memory cache
        if self.memory_cache:
            # Remove prefix for memory cache
            memory_key = key.replace(self.key_prefix, "")
            self.memory_cache.set(memory_key, value)
            logger.debug(f"Cached to memory with key: {key[:20]}...")
            return True

        return False

    def delete(self, key: str) -> bool:
        """Delete a cache entry.

        Args:
            key: Cache key

        Returns:
            True if deleted
        """
        deleted = False

        # Try Redis
        if self.redis_client:
            try:
                result = self.redis_client.delete(key)
                if result > 0:
                    deleted = True
                    logger.debug(f"Deleted from Redis: {key[:20]}...")
            except RedisError as e:
                logger.error(f"Redis delete error: {e}")

        # Also delete from memory cache
        if self.memory_cache:
            memory_key = key.replace(self.key_prefix, "")
            if memory_key in self.memory_cache.cache:
                del self.memory_cache.cache[memory_key]
                deleted = True
                logger.debug(f"Deleted from memory: {key[:20]}...")

        return deleted

    def clear_pattern(self, pattern: str) -> int:
        """Clear all cache entries matching a pattern.

        Args:
            pattern: Pattern to match (e.g., "lookup:llm:project_*")

        Returns:
            Number of entries cleared
        """
        count = 0

        # Clear from Redis
        if self.redis_client:
            try:
                # Use SCAN to find matching keys
                cursor = 0
                while True:
                    cursor, keys = self.redis_client.scan(
                        cursor=cursor, match=pattern, count=100
                    )
                    if keys:
                        count += self.redis_client.delete(*keys)
                    if cursor == 0:
                        break

                logger.info(f"Cleared {count} entries from Redis matching: {pattern}")
            except RedisError as e:
                logger.error(f"Redis clear pattern error: {e}")

        # Clear from memory cache
        if self.memory_cache:
            # Remove prefix from pattern
            memory_pattern = pattern.replace(self.key_prefix, "")
            keys_to_delete = [
                k
                for k in self.memory_cache.cache.keys()
                if self._match_pattern(k, memory_pattern)
            ]
            for key in keys_to_delete:
                del self.memory_cache.cache[key]
                count += 1

            logger.info(f"Cleared {len(keys_to_delete)} entries from memory")

        return count

    def _match_pattern(self, key: str, pattern: str) -> bool:
        """Simple pattern matching for memory cache.

        Args:
            key: Key to check
            pattern: Pattern with * wildcards

        Returns:
            True if matches
        """
        import fnmatch

        return fnmatch.fnmatch(key, pattern)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary of cache statistics
        """
        stats = {
            "backend": "redis" if self.redis_client else "memory",
            "ttl_hours": self.ttl_seconds // 3600,
            "key_prefix": self.key_prefix,
        }

        # Get Redis stats
        if self.redis_client:
            try:
                info = self.redis_client.info("stats")
                stats["redis"] = {
                    "total_connections": info.get("total_connections_received", 0),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0),
                    "hit_rate": self._calculate_hit_rate(
                        info.get("keyspace_hits", 0), info.get("keyspace_misses", 0)
                    ),
                }

                # Get key count
                dbinfo = self.redis_client.info("keyspace")
                db_key = f"db{self.redis_client.connection_pool.connection_kwargs.get('db', 0)}"
                if db_key in dbinfo:
                    stats["redis"]["total_keys"] = dbinfo[db_key].get("keys", 0)

            except RedisError as e:
                logger.error(f"Failed to get Redis stats: {e}")
                stats["redis"] = {"error": str(e)}

        # Get memory cache stats
        if self.memory_cache:
            stats["memory"] = {
                "entries": len(self.memory_cache.cache),
                "size_estimate": sum(
                    len(k) + len(v[0]) for k, v in self.memory_cache.cache.items()
                ),
            }

        return stats

    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """Calculate cache hit rate."""
        total = hits + misses
        return (hits / total) if total > 0 else 0.0

    def _update_stats(self, stat_type: str) -> None:
        """Update internal statistics.

        Args:
            stat_type: Type of stat to update ('hits', 'misses', 'sets')
        """
        # This could be extended to track more detailed statistics
        pass

    def cleanup_expired(self) -> int:
        """Clean up expired entries.

        For Redis, this happens automatically with TTL.
        For memory cache, we clean up lazily.

        Returns:
            Number of entries cleaned up
        """
        count = 0

        # Redis handles expiration automatically
        if self.redis_client:
            logger.debug("Redis handles expiration automatically")

        # Clean memory cache
        if self.memory_cache:
            current_time = time.time()
            keys_to_delete = []

            for key, (value, expiry) in list(self.memory_cache.cache.items()):
                if current_time >= expiry:
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                del self.memory_cache.cache[key]
                count += 1

            if count > 0:
                logger.info(f"Cleaned up {count} expired entries from memory cache")

        return count

    def warmup(self, project_id: str, preload_data: dict[str, str]) -> int:
        """Warm up cache with preloaded data.

        Args:
            project_id: Project ID for namespacing
            preload_data: Dictionary of prompt->response to preload

        Returns:
            Number of entries preloaded
        """
        count = 0

        for prompt, response in preload_data.items():
            # Generate key with project namespace
            key = f"{self.key_prefix}project:{project_id}:{hashlib.md5(prompt.encode()).hexdigest()}"

            if self.set(key, response):
                count += 1

        logger.info(f"Warmed up cache with {count} entries for project {project_id}")
        return count
