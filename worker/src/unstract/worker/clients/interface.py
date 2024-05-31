import logging
from abc import ABC, abstractmethod
from typing import Any

from docker.models.containers import Container


class ContainerClientInterface(ABC):

    @abstractmethod
    def __init__(self, image_name: str, image_tag: str, logger: logging.Logger) -> None:
        pass

    @abstractmethod
    def run_container(self, config: dict[Any, Any]) -> Container:
        """Method to run a container with provided config.

        Args:
            config (dict[Any, Any]): Configuration for container.

        Returns:
            Container: Returns a Container instance.
        """
        pass

    @abstractmethod
    def get_image() -> str:
        """Consturct image name with tag and repo name. Pulls the image if
        needed.

        Returns:
            str: full image name with tag.
        """
        pass
