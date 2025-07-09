from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


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
    def cleanup(self, client: ContainerClientInterface | None = None) -> None:
        """Stops and removes the running container."""
        pass

    @abstractmethod
    def graceful_stop(self, timeout: int = 300) -> None:
        """Gracefully stop the container with SIGTERM and timeout.

        Args:
            timeout (int): Grace period in seconds before force kill (default: 300)
        """
        pass


class ContainerClientInterface(ABC):
    @abstractmethod
    def __init__(
        self,
        image_name: str,
        image_tag: str,
        logger: logging.Logger,
        sidecar_enabled: bool = False,
    ) -> None:
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
    def run_container_with_sidecar(
        self, container_config: dict[Any, Any], sidecar_config: dict[Any, Any]
    ) -> tuple[ContainerInterface, ContainerInterface | None]:
        """Method to run a container with provided config. This method will run
        the container.

        Args:
            container_config (dict[Any, Any]): Configuration for container.
            sidecar_config (dict[Any, Any]): Configuration for sidecar.

        Returns:
            tuple[ContainerInterface, Optional[ContainerInterface]]:
                Returns a Container instance.
        """
        pass

    @abstractmethod
    def get_image(self) -> str:
        """Construct image name with tag and repo name. Pulls the image if
        needed.

        Returns:
            str: full image name with tag.
        """
        pass

    @abstractmethod
    def wait_for_container_stop(
        self,
        container: ContainerInterface | None,
        main_container_status: dict | None = None,
    ) -> dict | None:
        """Wait for the container to stop and return the exit code.

        Args:
            container (Optional[ContainerInterface]): The container to wait for.
            main_container_status (Optional[dict]): The status of the main container.

        Returns:
            str: The exit code of the container.
        """
        pass

    @abstractmethod
    def get_container_run_config(
        self,
        command: list[str],
        file_execution_id: str,
        shared_log_dir: str,
        container_name: str | None = None,
        envs: dict[str, Any] | None = None,
        auto_remove: bool = False,
        sidecar: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        """Generate the configuration dictionary to run the container.

        Returns:
            dict[str, Any]: Configuration for running the container.
        """
        pass

    @abstractmethod
    def cleanup_volume(self) -> None:
        """Cleans up the shared volume"""
        pass

    @abstractmethod
    def get_container_status(self, container_name: str) -> str:
        """Get the status of the container."""
        pass

    @abstractmethod
    def remove_container_by_name(
        self, container_name: str, with_sidecar: bool = False, force: bool = True
    ) -> bool:
        """Remove a container by its name.

        Args:
            container_name (str): Name of the container to remove.
            with_sidecar (bool, optional): Remove sidecar container if running. Defaults to False.
            force (bool, optional): Force removal if running. Defaults to True.

        Returns:
            bool: True if container was removed or not found, False if error.
        """
        pass

    @abstractmethod
    def graceful_stop_container(
        self, container: ContainerInterface | None, timeout: int | None = None
    ) -> None:
        """Gracefully stop a container with configurable timeout.

        Sends SIGTERM signal to container and waits for graceful shutdown.
        Falls back to force kill if timeout is exceeded.

        Args:
            container (ContainerInterface): Container to stop gracefully
            timeout (int, optional): Grace period in seconds.
                                   Defaults to GRACEFUL_SHUTDOWN_PERIOD env var or 300.
        """
        pass
