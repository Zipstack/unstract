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
    def can_receive_email() -> bool:
        """Whether connector supports receiving emails."""
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
