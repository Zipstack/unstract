import logging
import os
from typing import Any

import redis
from django.conf import settings

from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.queues.unstract_queue import UnstractQueue

logger = logging.getLogger(__name__)


class RedisConnectionManager:
    def __init__(self, get_engine):
        self.get_engine = get_engine

    def __enter__(self):
        self.conn = self.get_engine()
        return self.conn

    def __exit__(self, exc_type, exc_value, traceback):
        if self.conn:
            self.conn.close()


class RedisQueue(UnstractQueue):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("RedisQueue")

    @staticmethod
    def get_id() -> str:
        return "redisqueue|79e1d681-9b8b-4f6b-b972-1a6a095312f45"

    @staticmethod
    def get_name() -> str:
        return "Redis Queue"

    @staticmethod
    def get_description() -> str:
        return "Redis Queue"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/Redis.png"

    @staticmethod
    def get_json_schema() -> str:
        f = open(f"{os.path.dirname(__file__)}/static/json_schema.json")
        schema = f.read()
        f.close()
        return schema

    @staticmethod
    def can_write() -> bool:
        return True

    @staticmethod
    def can_read() -> bool:
        return True

    def get_engine(self) -> redis.Redis:
        """
        Establish a connection to the Redis server.

        Returns:
            Redis: A Redis connection object.

        Raises:
            ConnectorError: If there is an error connecting to Redis.
        """
        try:
            con = redis.Redis(
                host=settings.MANUAL_REVIEW_REDIS_HOST,
                port=int(settings.MANUAL_REVIEW_REDIS_PORT),
                username=settings.MANUAL_REVIEW_REDIS_USER,
                password=settings.MANUAL_REVIEW_REDIS_PASSWORD,
            )
            return con
        except Exception as e:
            raise ConnectorError(f"Error connecting to Redis: {e}") from e

    def enqueue(self, queue_name: str, message: str) -> Any:
        """
        Add a message to the specified queue.

        Args:
            queue_name (str): The name of the queue.
            message (str): The message to be added.

        Raises:
            ConnectorError: If there is an error adding the message to the queue.
        """
        try:
            with RedisConnectionManager(self.get_engine) as conn:
                conn.lpush(queue_name, message)
        except Exception as e:
            raise ConnectorError(f"Error adding message to queue: {e}") from e

    def dequeue(self, queue_name: str, timeout: int = 5) -> Any:
        """
        Remove and return a message from the specified queue.

        Args:
            queue_name (str): The name of the queue.
            timeout (int): The timeout in seconds for the brpop operation.
            Default is 5 seconds.

        Returns:
            Any: The message from the queue, or None if the timeout is reached.

        Raises:
            ConnectorError: If there is an error removing the message from the queue.
        """
        try:
            with RedisConnectionManager(self.get_engine) as conn:
                message = conn.brpop(queue_name, timeout=timeout)
                if message is None:
                    logger.debug(
                        f"No message received from queue '{queue_name}' "
                        f"within {timeout} seconds.",
                        stack_info=True,
                        exc_info=True,
                    )
                    return None
                return message[1]
        except Exception as e:
            raise ConnectorError(f"Error removing message from queue: {e}") from e

    def peek(self, queue_name: str) -> Any:
        """
        Retrieve, but do not remove, the first message in the specified queue.

        Args:
            queue_name (str): The name of the queue.

        Returns:
            Any: The first message in the queue.

        Raises:
            ConnectorError: If there is an error retrieving the message from the queue.
        """
        try:
            with RedisConnectionManager(self.get_engine) as conn:
                message = conn.lindex(
                    queue_name, 0
                )  # Get the first item without removing it
                return message
        except Exception as e:
            raise ConnectorError(f"Error peeking message in queue: {e}") from e

    def lset(self, queue_name: str, index: int, value: str) -> None:
        """
        Set the value at a specific index in the specified queue.

        Args:
            queue_name (str): The name of the queue.
            index (int): The index at which the value should be set.
            value (str): The value to be set.

        Raises:
            ConnectorError: If there is an error setting the value in the queue.
        """
        try:
            with RedisConnectionManager(self.get_engine) as conn:
                conn.lset(queue_name, index, value)  # Set the value at a specific index
        except Exception as e:
            raise ConnectorError(f"Error setting value in queue: {e}") from e

    def llen(self, queue_name: str) -> int:
        """
        Return the length of the specified queue.

        Args:
            queue_name (str): The name of the queue.

        Returns:
            int: The length of the queue.

        Raises:
            ConnectorError: If there is an error retrieving the length of the queue.
        """
        try:
            with RedisConnectionManager(self.get_engine) as conn:
                length = conn.llen(queue_name)
                return length
        except Exception as e:
            raise ConnectorError(f"Error retrieving length of queue: {e}") from e

    def lindex(self, queue_name: str, index: int) -> Any:
        """
        Retrieve the value at a specific index in the specified queue.

        Args:
            queue_name (str): The name of the queue.
            index (int): The index of the element to retrieve.

        Returns:
            Any: The value at the specified index in the queue, or None if the index is
            out of range.

        Raises:
            ConnectorError: If there is an error retrieving the value from the queue.
        """
        try:
            with RedisConnectionManager(self.get_engine) as conn:
                value = conn.lindex(queue_name, index)
                return value
        except Exception as e:
            raise ConnectorError(
                f"Error retrieving value from queue at index {index}: {e}"
            ) from e

    def keys(self, pattern: str = "*") -> list[str]:
        """
        Retrieve all keys matching the specified pattern.

        Args:
            pattern (str): The pattern to match keys against. Defaults to '*'.

        Returns:
            List[str]: A list of keys matching the pattern.

        Raises:
            ConnectorError: If there is an error retrieving the keys.
        """
        try:
            with RedisConnectionManager(self.get_engine) as conn:
                keys = conn.keys(pattern)
                return keys
        except Exception as e:
            raise ConnectorError(
                f"Error retrieving keys with pattern '{pattern}': {e}"
            ) from e
