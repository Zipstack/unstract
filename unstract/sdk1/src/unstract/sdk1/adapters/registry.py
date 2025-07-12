from abc import ABC, abstractmethod
from typing import Any


class AdapterRegistry(ABC):
    def __init__(self, name: str):
        self.name = name

    @staticmethod
    @abstractmethod
    def register_adapters(adapters: dict[str, Any]) -> None:
        pass
