from abc import ABC, abstractmethod
from typing import Any


class ContainerClientInterface(ABC):

    @abstractmethod
    def __init__(self, image_name: str, image_tag: str) -> None:
        pass

    @abstractmethod
    def run_container(config: dict[Any, Any]):
        """Method to run a container with provided config.

        Args:
            config (dict[Any, Any]): Configuration for container.
        """
        pass
