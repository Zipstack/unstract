"""Base Redis Client for Workers

Provides a comprehensive Redis client with all common Redis operations.
This serves as the foundation for specialized clients (queue, cache, etc.).
"""

import logging
from typing import Any

import redis

logger = logging.getLogger(__name__)


class RedisClient:
    """Base Redis client with comprehensive operations."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        username: str | None = None,
        password: str | None = None,
        db: int = 0,
        decode_responses: bool = True,
        socket_connect_timeout: int = 5,
        socket_timeout: int = 5,
    ):
        """Initialize Redis client.

        Args:
            host: Redis host
            port: Redis port
            username: Redis username (optional)
            password: Redis password (optional)
            db: Redis database number
            decode_responses: Whether to decode responses to strings
            socket_connect_timeout: Connection timeout in seconds
            socket_timeout: Socket timeout in seconds
        """
        self.redis_client = redis.Redis(
            host=host,
            port=port,
            username=username,
            password=password,
            db=db,
            decode_responses=decode_responses,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
        )

    # Basic key-value operations
    def get(self, key: str) -> Any:
        """Get value by key.

        Args:
            key: Redis key

        Returns:
            Value or None if key doesn't exist
        """
        return self.redis_client.get(key)

    def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """Set key to value.

        Args:
            key: Redis key
            value: Value to set
            ex: Expire time in seconds
            px: Expire time in milliseconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists

        Returns:
            True if set successfully
        """
        return self.redis_client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)

    def setex(self, key: str, time: int, value: Any) -> bool:
        """Set key with expiration time.

        Args:
            key: Redis key
            time: Expiration time in seconds
            value: Value to set

        Returns:
            True if set successfully
        """
        return self.redis_client.setex(key, time, value)

    def delete(self, *keys: str) -> int:
        """Delete one or more keys.

        Args:
            *keys: Keys to delete

        Returns:
            Number of keys deleted
        """
        return self.redis_client.delete(*keys)

    def exists(self, *keys: str) -> int:
        """Check if keys exist.

        Args:
            *keys: Keys to check

        Returns:
            Number of keys that exist
        """
        return self.redis_client.exists(*keys)

    # TTL operations
    def expire(self, key: str, time: int) -> bool:
        """Set expiration time on key.

        Args:
            key: Redis key
            time: Expiration time in seconds

        Returns:
            True if timeout was set
        """
        return self.redis_client.expire(key, time)

    def ttl(self, key: str) -> int:
        """Get time to live for key.

        Args:
            key: Redis key

        Returns:
            TTL in seconds, -1 if no expiry, -2 if key doesn't exist
        """
        return self.redis_client.ttl(key)

    def persist(self, key: str) -> bool:
        """Remove expiration from key.

        Args:
            key: Redis key

        Returns:
            True if expiration was removed
        """
        return self.redis_client.persist(key)

    # Batch operations
    def mget(self, keys: list[str]) -> list[Any]:
        """Get multiple values at once.

        Args:
            keys: List of Redis keys

        Returns:
            List of values (None for non-existent keys)
        """
        return self.redis_client.mget(keys)

    def mset(self, mapping: dict[str, Any]) -> bool:
        """Set multiple key-value pairs at once.

        Args:
            mapping: Dictionary of key-value pairs

        Returns:
            True if all keys were set
        """
        return self.redis_client.mset(mapping)

    # Key scanning and patterns
    def keys(self, pattern: str = "*") -> list[str]:
        """Get all keys matching pattern.

        Warning: Use scan() for production - keys() blocks the server.

        Args:
            pattern: Key pattern (supports wildcards)

        Returns:
            List of matching keys
        """
        return self.redis_client.keys(pattern)

    def scan(
        self, cursor: int = 0, match: str | None = None, count: int | None = None
    ) -> tuple[int, list[str]]:
        """Incrementally iterate over keys (non-blocking).

        Args:
            cursor: Cursor position (0 to start)
            match: Key pattern to match
            count: Approximate number of keys to return

        Returns:
            Tuple of (next_cursor, list_of_keys)
        """
        return self.redis_client.scan(cursor=cursor, match=match, count=count)

    # Pipeline support
    def pipeline(self, transaction: bool = True) -> redis.client.Pipeline:
        """Create a pipeline for batching commands.

        Args:
            transaction: Whether to use MULTI/EXEC transaction

        Returns:
            Redis pipeline object
        """
        return self.redis_client.pipeline(transaction=transaction)

    # Health check
    def ping(self) -> bool:
        """Check Redis connectivity.

        Returns:
            True if connected, False otherwise
        """
        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False

    # Connection info
    def info(self, section: str | None = None) -> dict[str, Any]:
        """Get Redis server information.

        Args:
            section: Specific info section (e.g., 'memory', 'stats')

        Returns:
            Dictionary of server information
        """
        return self.redis_client.info(section=section)

    @classmethod
    def from_env(cls) -> "RedisClient":
        """Create client from environment variables.

        Environment variables:
            REDIS_HOST: Redis host (default: localhost)
            REDIS_PORT: Redis port (default: 6379)
            REDIS_USER: Redis username (optional)
            REDIS_USERNAME: Redis username (optional, alternative to REDIS_USER)
            REDIS_PASSWORD: Redis password (optional)
            REDIS_DB: Redis database number (default: 0)

        Returns:
            Configured RedisClient instance
        """
        import os

        return cls(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            username=os.getenv("REDIS_USER") or os.getenv("REDIS_USERNAME"),
            password=os.getenv("REDIS_PASSWORD"),
            db=int(os.getenv("REDIS_DB", "0")),
        )
