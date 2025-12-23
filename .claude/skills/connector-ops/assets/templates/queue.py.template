"""
Queue Connector Template

Replace placeholders:
- {ClassName}: PascalCase class name (e.g., RedisQueue, RabbitMQ)
- {connector_name}: lowercase connector name (e.g., redis_queue, rabbitmq)
- {display_name}: Display name (e.g., "Redis Queue", "RabbitMQ")
- {description}: Brief description
- {uuid}: Generated UUID (use uuid4())
- {icon_name}: Icon filename (e.g., "Redis.png")
- {queue_lib}: Python library for queue (e.g., redis, pika)
"""

import os
from typing import Any

from unstract.connectors.queues.unstract_queue import UnstractQueue
from unstract.connectors.exceptions import ConnectorError


class {ClassName}(UnstractQueue):
    """
    {display_name} queue connector.

    {description}
    """

    def __init__(self, settings: dict[str, Any]):
        super().__init__("{display_name}")

        # Connection settings
        self.host = settings.get("host", "localhost")
        self.port = settings.get("port", "{default_port}")
        self.password = settings.get("password", "")
        self.database = settings.get("database", "0")  # For Redis

        # SSL settings
        self.ssl_enabled = settings.get("sslEnabled", False)

        # Connection pool
        self._client = None

    @staticmethod
    def get_id() -> str:
        return "{connector_name}|{uuid}"

    @staticmethod
    def get_name() -> str:
        return "{display_name}"

    @staticmethod
    def get_description() -> str:
        return "{description}"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/{icon_name}"

    @staticmethod
    def get_json_schema() -> str:
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "static",
            "json_schema.json"
        )
        with open(schema_path, "r") as f:
            return f.read()

    @staticmethod
    def can_write() -> bool:
        return True

    @staticmethod
    def can_read() -> bool:
        return True

    @staticmethod
    def requires_oauth() -> bool:
        return False

    @staticmethod
    def python_social_auth_backend() -> str:
        return ""

    def get_engine(self) -> Any:
        """
        Return queue client connection.

        Returns:
            Queue client instance
        """
        if self._client is not None:
            return self._client

        # Import here for fork safety
        import {queue_lib}

        try:
            self._client = {queue_lib}.{ClientClass}(
                host=self.host,
                port=int(self.port),
                password=self.password or None,
                # db=int(self.database),  # For Redis
                # ssl=self.ssl_enabled,
            )

            # Test connection
            self._client.ping()

            return self._client

        except Exception as e:
            raise ConnectorError(
                f"Failed to connect to {display_name}: {str(e)}",
                treat_as_user_message=True
            ) from e

    def test_credentials(self) -> bool:
        """
        Test queue credentials.

        Returns:
            True if connection successful

        Raises:
            ConnectorError: If connection fails
        """
        try:
            client = self.get_engine()
            client.ping()
            return True
        except Exception as e:
            raise ConnectorError(
                f"Connection test failed: {str(e)}",
                treat_as_user_message=True
            ) from e

    def enqueue(self, queue_name: str, message: str) -> Any:
        """
        Add message to queue.

        Args:
            queue_name: Name of the queue
            message: Message to enqueue

        Returns:
            Result from queue operation
        """
        try:
            client = self.get_engine()
            # Adapt for specific queue library:
            # Redis: client.lpush(queue_name, message)
            # RabbitMQ: channel.basic_publish(...)
            return client.lpush(queue_name, message)
        except Exception as e:
            raise ConnectorError(f"Failed to enqueue message: {str(e)}") from e

    def dequeue(self, queue_name: str, timeout: int = 5) -> Any:
        """
        Get and remove message from queue.

        Args:
            queue_name: Name of the queue
            timeout: Timeout in seconds for blocking operation

        Returns:
            Message from queue or None if timeout
        """
        try:
            client = self.get_engine()
            # Adapt for specific queue library:
            # Redis: client.brpop(queue_name, timeout)
            result = client.brpop(queue_name, timeout=timeout)
            if result:
                return result[1].decode("utf-8")
            return None
        except Exception as e:
            raise ConnectorError(f"Failed to dequeue message: {str(e)}") from e

    def peek(self, queue_name: str) -> Any:
        """
        View next message without removing it.

        Args:
            queue_name: Name of the queue

        Returns:
            Next message or None if queue empty
        """
        try:
            client = self.get_engine()
            # Adapt for specific queue library:
            # Redis: client.lindex(queue_name, -1)
            result = client.lindex(queue_name, -1)
            if result:
                return result.decode("utf-8")
            return None
        except Exception as e:
            raise ConnectorError(f"Failed to peek message: {str(e)}") from e
