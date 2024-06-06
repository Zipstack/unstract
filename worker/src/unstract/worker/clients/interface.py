import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class ContainerInterface(ABC):

    @abstractmethod
    def logs(self, follow=False) -> Iterator[str]:
        """Returns an iterator object of logs.

        Args:
            follow (bool, optional): Should the logs be followed. Defaults to False.

        Yields:
            Iterator[str]: Yields logs line by line.
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Stops and removes the running container."""
        pass


class ContainerClientInterface(ABC):

    @abstractmethod
    def __init__(self, image_name: str, image_tag: str, logger: logging.Logger) -> None:
        pass

    @abstractmethod
    def run_container(self, config: dict[Any, Any]) -> ContainerInterface:
        """Method to run a container with provided config. This method will run
        the container.

        Args:
            config (dict[Any, Any]): Configuration for container.

        Returns:
            Container: Returns a Container instance.
        """
        pass

    @abstractmethod
    def get_image(self) -> str:
        """Consturct image name with tag and repo name. Pulls the image if
        needed.

        Returns:
            str: full image name with tag.
        """
        pass
