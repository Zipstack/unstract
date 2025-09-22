import logging
from abc import ABC, abstractmethod

from unstract.sdk1.adapters.enums import AdapterTypes

logger = logging.getLogger(__name__)


class Adapter(ABC):
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

    @classmethod
    def get_json_schema(cls) -> str:
        schema_path = getattr(cls, "SCHEMA_PATH", None)
        if schema_path is None:
            raise ValueError(f"SCHEMA_PATH not defined for {cls.__name__}")
        with open(schema_path) as f:
            return f.read()

    @staticmethod
    @abstractmethod
    def get_adapter_type() -> AdapterTypes:
        return ""

    @abstractmethod
    def test_connection(self) -> bool:
        """Override to test connection for a adapter.

        Returns:
            bool: Flag indicating if the credentials are valid or not
        """
        pass
