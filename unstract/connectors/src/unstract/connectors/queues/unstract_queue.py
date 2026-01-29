import logging
from abc import ABC, abstractmethod
from typing import Any

from unstract.connectors.base import UnstractConnector
from unstract.connectors.enums import ConnectorMode


class UnstractQueue(UnstractConnector, ABC):
    """Abstract class for queue connector."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    )

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    @staticmethod
    def get_id() -> str:
        return ""

    @staticmethod
    def get_name() -> str:
        return ""

    @staticmethod
    def get_description() -> str:
        return ""

    @staticmethod
    def get_icon() -> str:
        return ""

    @staticmethod
    def get_json_schema() -> str:
        return ""

    @staticmethod
    def can_write() -> bool:
        return False

    @staticmethod
    def can_read() -> bool:
        return False

    @staticmethod
    def requires_oauth() -> bool:
        return False

    @staticmethod
    def python_social_auth_backend() -> str:
        return ""

    @staticmethod
    def get_connector_mode() -> ConnectorMode:
        return ConnectorMode.MANUAL_REVIEW

    def test_credentials(self) -> bool:
        """Override to test credentials for a connector."""
        return True

    @abstractmethod
    def get_engine(self) -> Any:
        pass

    @abstractmethod
    def enqueue(self, queue_name: str, message: str) -> Any:
        pass

    @abstractmethod
    def dequeue(self, queue_name: str, timeout: int = 5) -> Any:
        pass

    @abstractmethod
    def peek(self, queue_name: str) -> Any:
        pass

    @abstractmethod
    def lset(self, queue_name: str, index: int, value: str) -> None:
        pass

    @abstractmethod
    def llen(self, queue_name: str) -> int:
        pass

    @abstractmethod
    def lindex(self, queue_name: str, index: int) -> Any:
        pass

    @abstractmethod
    def keys(self, pattern: str = "*") -> list[str]:
        pass

    @abstractmethod
    def lrange(self, queue_name: str, start: int, end: int) -> list[Any]:
        """Retrieve a range of elements from a queue.

        Args:
            queue_name: Name of the queue to read from
            start: Starting index (inclusive, 0-based)
            end: Ending index (inclusive, -1 for last element)

        Returns:
            List of elements in the specified range. Returns empty list
            for invalid ranges (e.g., start > end) or if queue is empty.

        Note:
            Supports Redis-style negative indexing where -1 represents
            the last element, -2 the second to last, etc.
        """
        pass

    @abstractmethod
    def dequeue_batch(self, queue_name: str, count: int) -> list[Any]:
        """Dequeue multiple items from a queue in a single operation.

        Args:
            queue_name: Name of the queue to dequeue from
            count: Maximum number of items to dequeue (must be > 0)

        Returns:
            List of dequeued items in FIFO order (oldest first).
            May contain fewer items than count if queue has fewer items.
            Returns empty list if queue is empty or count <= 0.

        Raises:
            ValueError: If count is negative

        Note:
            This is a non-blocking operation with best-effort semantics.
            Items are returned in the order they were enqueued (FIFO).
        """
        pass
