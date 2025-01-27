import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any, Optional


class ContainerInterface(ABC):
    @property
    @abstractmethod
    def name(self):
        """The name of the container."""
        pass

    @abstractmethod
    def logs(self, follow=True) -> Iterator[str]:
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

    @abstractmethod
    def get_container_run_config(
        self,
        command: list[str],
        organization_id: str,
        workflow_id: str,
        execution_id: str,
        run_id: str,
        envs: Optional[dict[str, Any]] = None,
        auto_remove: bool = False,
        execution_attempt: int = 1,
    ) -> dict[str, Any]:
        """Generate the configuration dictionary to run the container.

        Returns:
            dict[str, Any]: Configuration for running the container.
        """
        pass
