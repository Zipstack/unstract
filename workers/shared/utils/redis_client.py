"""Lightweight Redis Queue Client for Workers

Provides simple queue operations (LLEN, LPOP, RPUSH) for workers
that need basic Redis queue functionality without heavy dependencies.
"""

import logging
from typing import Any

import redis

logger = logging.getLogger(__name__)


class RedisQueueClient:
    """Lightweight Redis client for queue operations."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        username: str | None = None,
        password: str | None = None,
        db: int = 0,
        decode_responses: bool = True,
    ):
        """Initialize Redis queue client.

        Args:
            host: Redis host
            port: Redis port
            username: Redis username (optional)
            password: Redis password (optional)
            db: Redis database number
            decode_responses: Whether to decode responses to strings
        """
        self.redis_client = redis.Redis(
            host=host,
            port=port,
            username=username,
            password=password,
            db=db,
            decode_responses=decode_responses,
            socket_connect_timeout=5,
            socket_timeout=5,
        )

    def llen(self, queue_name: str) -> int:
        """Get queue length.

        Args:
            queue_name: Name of the queue

        Returns:
            Number of items in queue
        """
        return self.redis_client.llen(queue_name)

    def lpop(self, queue_name: str) -> Any:
        """Pop item from left of queue.

        Args:
            queue_name: Name of the queue

        Returns:
            Item from queue or None if empty
        """
        return self.redis_client.lpop(queue_name)

    def rpush(self, queue_name: str, *values) -> int:
        """Push items to right of queue.

        Args:
            queue_name: Name of the queue
            *values: Values to push

        Returns:
            New queue length
        """
        return self.redis_client.rpush(queue_name, *values)

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

    @classmethod
    def from_env(cls) -> "RedisQueueClient":
        """Create client from environment variables.

        Returns:
            Configured RedisQueueClient instance
        """
        import os

        return cls(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            username=os.getenv("REDIS_USER"),
            password=os.getenv("REDIS_PASSWORD"),
        )
