"""Redis Queue Client for Workers

Specialized Redis client for queue operations (LPOP, RPUSH, etc.).
Inherits from RedisClient for basic Redis functionality.
"""

import logging
from typing import Any

from unstract.core.cache.redis_client import RedisClient

logger = logging.getLogger(__name__)


class RedisQueueClient(RedisClient):
    """Redis client specialized for queue operations.

    Inherits all basic Redis operations from RedisClient and adds
    queue-specific list operations (LPOP, RPUSH, LLEN, etc.).
    """

    # Queue operations (List operations)
    def llen(self, queue_name: str) -> int:
        """Get queue length.

        Args:
            queue_name: Name of the queue (list key)

        Returns:
            Number of items in queue
        """
        return self.redis_client.llen(queue_name)

    def lpop(self, queue_name: str, count: int | None = None) -> Any:
        """Pop item(s) from left (head) of queue.

        Args:
            queue_name: Name of the queue
            count: Number of items to pop (Redis 6.2+, optional)

        Returns:
            Item from queue or None if empty
            If count is specified, returns list of items
        """
        if count is not None:
            return self.redis_client.lpop(queue_name, count=count)
        return self.redis_client.lpop(queue_name)

    def rpop(self, queue_name: str, count: int | None = None) -> Any:
        """Pop item(s) from right (tail) of queue.

        Args:
            queue_name: Name of the queue
            count: Number of items to pop (Redis 6.2+, optional)

        Returns:
            Item from queue or None if empty
            If count is specified, returns list of items
        """
        if count is not None:
            return self.redis_client.rpop(queue_name, count=count)
        return self.redis_client.rpop(queue_name)

    def lpush(self, queue_name: str, *values) -> int:
        """Push items to left (head) of queue.

        Args:
            queue_name: Name of the queue
            *values: Values to push

        Returns:
            New queue length
        """
        return self.redis_client.lpush(queue_name, *values)

    def rpush(self, queue_name: str, *values) -> int:
        """Push items to right (tail) of queue.

        Args:
            queue_name: Name of the queue
            *values: Values to push

        Returns:
            New queue length
        """
        return self.redis_client.rpush(queue_name, *values)

    def lrange(self, queue_name: str, start: int, end: int) -> list[Any]:
        """Get range of items from queue without removing them.

        Args:
            queue_name: Name of the queue
            start: Start index (0-based)
            end: End index (-1 for last item)

        Returns:
            List of items in the specified range
        """
        return self.redis_client.lrange(queue_name, start, end)

    def lrem(self, queue_name: str, count: int, value: Any) -> int:
        """Remove items from queue by value.

        Args:
            queue_name: Name of the queue
            count: Number of occurrences to remove
                   count > 0: Remove from head to tail
                   count < 0: Remove from tail to head
                   count = 0: Remove all occurrences
            value: Value to remove

        Returns:
            Number of items removed
        """
        return self.redis_client.lrem(queue_name, count, value)

    def blpop(
        self, queue_names: list[str] | str, timeout: int = 0
    ) -> tuple[str, Any] | None:
        """Blocking left pop - wait for item to be available.

        Args:
            queue_names: Single queue name or list of queue names
            timeout: Timeout in seconds (0 = wait forever)

        Returns:
            Tuple of (queue_name, value) or None if timeout
        """
        if isinstance(queue_names, str):
            queue_names = [queue_names]
        return self.redis_client.blpop(queue_names, timeout=timeout)

    def brpop(
        self, queue_names: list[str] | str, timeout: int = 0
    ) -> tuple[str, Any] | None:
        """Blocking right pop - wait for item to be available.

        Args:
            queue_names: Single queue name or list of queue names
            timeout: Timeout in seconds (0 = wait forever)

        Returns:
            Tuple of (queue_name, value) or None if timeout
        """
        if isinstance(queue_names, str):
            queue_names = [queue_names]
        return self.redis_client.brpop(queue_names, timeout=timeout)

    def ltrim(self, queue_name: str, start: int, end: int) -> bool:
        """Trim queue to specified range.

        Args:
            queue_name: Name of the queue
            start: Start index (0-based, inclusive)
            end: End index (-1 for last item, inclusive)

        Returns:
            True if successful
        """
        return self.redis_client.ltrim(queue_name, start, end)
