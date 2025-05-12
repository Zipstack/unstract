import logging
from abc import ABC, abstractmethod

from unstract.connectors.enums import ConnectorMode


class UnstractConnector(ABC):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    )

    def __init__(self, name: str):
        self.name = name

    @staticmethod
    @abstractmethod
    def get_id() -> str:
        return ""

    @staticmethod
    @abstractmethod
    def get_name() -> str:
        return ""

    @staticmethod
    @abstractmethod
    def get_description() -> str:
        return ""

    @staticmethod
    @abstractmethod
    def get_icon() -> str:
        return ""

    @staticmethod
    @abstractmethod
    def get_json_schema() -> str:
        return ""

    @staticmethod
    @abstractmethod
    def can_write() -> bool:
        return False

    @staticmethod
    @abstractmethod
    def can_read() -> bool:
        return False

    @staticmethod
    @abstractmethod
    def can_receive_email() -> bool:
        return False

    @staticmethod
    @abstractmethod
    def requires_oauth() -> bool:
        return False

    # TODO: Move into UnstractFileSystem instead
    @staticmethod
    @abstractmethod
    def python_social_auth_backend() -> str:
        return ""

    @staticmethod
    @abstractmethod
    def get_connector_mode() -> ConnectorMode:
        return ConnectorMode.UNKNOWN

    @abstractmethod
    def test_credentials(self) -> bool:
        """Override to test credentials for a connector.

        Returns:
            bool: Flag indicating if the credentials are valid or not
        """
        pass
