import logging
import os
from collections.abc import Iterator
from typing import Any, Optional

from docker.errors import APIError, ImageNotFound
from docker.models.containers import Container
from unstract.runner.clients.interface import (
    ContainerClientInterface,
    ContainerInterface,
)
from unstract.runner.constants import Env
from unstract.runner.utils import Utils

from docker import DockerClient
from unstract.core.utilities import UnstractUtils


class DockerContainer(ContainerInterface):
    def __init__(self, container: Container, logger: logging.Logger) -> None:
        self.container: Container = container
        self.logger = logger

    @property
    def name(self):
        return self.container.name

    def logs(self, follow=True) -> Iterator[str]:
        for line in self.container.logs(stream=True, follow=follow):
            yield line.decode().strip()

    def wait_until_stop(
        self, main_container_status: Optional[dict[str, Any]] = None
    ) -> dict:
        """Wait until the container stops and return the status.

        Returns:
            dict: Container exit status containing 'StatusCode' and 'Error' if any
        """
        if main_container_status and main_container_status.get("StatusCode", 0) != 0:
            self.logger.info(
                f"Main container exited with status {main_container_status}, "
                "stopping sidecar"
            )
            timeout = Utils.get_sidecar_wait_timeout()
            return self.container.wait(timeout=timeout)

        return self.container.wait()

    def cleanup(self, client: Optional[ContainerClientInterface] = None) -> None:
        if not self.container or not Utils.remove_container_on_exit():
            return
        try:
            self.container.remove(force=True)
            if client:
                client.cleanup_volume()
        except Exception as remove_error:
            self.logger.error(f"Failed to remove docker container: {remove_error}")


class Client(ContainerClientInterface):
    def __init__(
        self,
        image_name: str,
        image_tag: str,
        logger: logging.Logger,
        sidecar_enabled: bool = False,
    ) -> None:
        self.image_name = image_name
        self.sidecar_image_name = os.getenv(Env.TOOL_SIDECAR_IMAGE_NAME)
        self.sidecar_image_tag = os.getenv(Env.TOOL_SIDECAR_IMAGE_TAG)
        # If no image_tag is provided will assume the `latest` tag
        self.image_tag = image_tag or "latest"
        self.logger = logger
        self.sidecar_enabled = sidecar_enabled
        self.volume_name: Optional[str] = None

        # Create a Docker client that communicates with
        #   the Docker daemon in the host environment
        self.client: DockerClient = DockerClient.from_env()
        self.__private_login()

    def __private_login(self):
        """Performs login for private registry if required."""
        private_registry_credential_path = os.getenv(
            Env.PRIVATE_REGISTRY_CREDENTIAL_PATH
        )
        private_registry_username = os.getenv(Env.PRIVATE_REGISTRY_USERNAME)
        private_registry_url = os.getenv(Env.PRIVATE_REGISTRY_URL)
        if not (
            private_registry_credential_path
            and private_registry_username
            and private_registry_url
        ):
            return
        try:
            self.logger.info(
                "Performing private docker login for %s.", private_registry_url
            )
            with open(private_registry_credential_path, encoding="utf-8") as file:
                password = file.read()
            self.client.login(
                username=private_registry_username,
                password=password,
                registry=private_registry_url,
            )
        except FileNotFoundError as file_err:
            self.logger.error(
                f"Service account key file is not mounted "
                f"in {private_registry_credential_path}: {file_err}"
                "Logging to private registry might fail, if private tool is used."
            )
        except APIError as api_err:
            self.logger.error(
                f"Exception occured while invoking docker client : {api_err}."
                f"Authentication to artifact registry failed."
            )
        except OSError as os_err:
            self.logger.error(
                f"Exception in the file system used for authentication: {os_err}"
            )
        except Exception as exc:
            self.logger.error(
                f"Internal service error occured while authentication: {exc}"
            )

    def __image_exists(self, image_name_with_tag: str) -> bool:
        """Check if the container image exists in system.

        Args:
            image_name_with_tag (str): The image name with tag.

        Returns:
            bool: True if the image exists, False otherwise.
        """

        try:
            # Attempt to get the image information
            self.client.images.get(image_name_with_tag)
            self.logger.info(
                f"Image '{image_name_with_tag}' found in the local system."
            )
            return True
        except ImageNotFound:  # type: ignore[attr-defined]
            self.logger.info(
                f"Image '{image_name_with_tag}' not found in the local system."
            )
            return False
        except APIError as e:  # type: ignore[attr-defined]
            self.logger.error(f"An API error occurred: {e}")
            return False

    def cleanup_volume(self) -> None:
        """Cleans up the shared volume after both containers are stopped."""
        try:
            if self.volume_name:
                self.client.volumes.get(self.volume_name).remove(force=True)
                self.logger.info(f"Removed log volume: {self.volume_name}")
        except Exception as e:
            self.logger.warning(f"Failed to remove log volume: {e}")

    def get_image(self, sidecar: bool = False) -> str:
        """Will check if image exists locally and pulls the image using
        `self.image_name` and `self.image_tag` if necessary.

        Returns:
            str: image string combining repo name and tag like `ubuntu:22.04`
        """
        if sidecar:
            image_name_with_tag = f"{self.sidecar_image_name}:{self.sidecar_image_tag}"
            repository = self.sidecar_image_name
        else:
            image_name_with_tag = f"{self.image_name}:{self.image_tag}"
            repository = self.image_name
        if self.__image_exists(image_name_with_tag):
            return image_name_with_tag

        self.logger.info("Pulling the container: %s", image_name_with_tag)
        resp = self.client.api.pull(
            repository=repository,
            tag=self.image_tag,
            stream=True,
            decode=True,
        )
        counter = 0
        for line in resp:
            # The counter is used to print status on every 100th status
            # Otherwise the output logs will be polluted.
            if counter < 100:
                counter += 1
                continue
            counter = 0
            self.logger.info(
                "CONTAINER PULL STATUS: %s - %s : %s",
                line.get("status"),
                line.get("id"),
                line.get("progress"),
            )
        self.logger.info("Finished pulling the container: %s", image_name_with_tag)

        return image_name_with_tag

    def get_container_run_config(
        self,
        command: list[str],
        file_execution_id: str,
        shared_log_dir: str,
        container_name: Optional[str] = None,
        envs: Optional[dict[str, Any]] = None,
        auto_remove: bool = False,
        sidecar: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        if envs is None:
            envs = {}

        # Create shared volume for logs
        volume_name = f"logs-{file_execution_id}"
        self.volume_name = volume_name

        # Ensure we're mounting to a directory
        mount_target = shared_log_dir
        if not mount_target.endswith("/"):
            mount_target = os.path.dirname(mount_target)
        if self.sidecar_enabled:
            mounts = [
                {
                    "Type": "volume",
                    "Source": volume_name,
                    "Target": mount_target,
                }
            ]
            stream_logs = False
        else:
            mounts = []
            stream_logs = True

        if not container_name:
            container_name = UnstractUtils.build_tool_container_name(
                tool_image=self.image_name,
                tool_version=self.image_tag,
                file_execution_id=file_execution_id,
            )

        if sidecar:
            container_name = f"{container_name}-sidecar"

        return {
            "name": container_name,
            "image": self.get_image(sidecar=sidecar),
            "command": command,
            "detach": True,
            "stream": stream_logs,
            "auto_remove": auto_remove,
            "environment": envs,
            "stderr": True,
            "stdout": True,
            "network": os.getenv(Env.TOOL_CONTAINER_NETWORK, ""),
            "mounts": mounts,
        }

    def run_container(self, container_config: dict[str, Any]) -> DockerContainer:
        """Run a container with the given configuration.

        Args:
            container_config (dict[str, Any]): Container configuration

        Returns:
            DockerContainer: Running container instance
        """
        try:
            self.logger.info("Running container with config: %s", container_config)
            container = self.client.containers.run(**container_config)
            return DockerContainer(
                container=container,
                logger=self.logger,
            )
        except ImageNotFound:
            self.logger.error(f"Image {self.image_name}:{self.image_tag} not found")
            raise

    def run_container_with_sidecar(
        self, container_config: dict[str, Any], sidecar_config: dict[str, Any]
    ) -> tuple[DockerContainer, Optional[DockerContainer]]:
        """Run a container with sidecar.

        Args:
            container_config (dict[str, Any]): Container configuration
            sidecar_config (dict[str, Any]): Sidecar configuration

        Returns:
            tuple[DockerContainer, Optional[DockerContainer]]:
                Running container and sidecar instance
        """
        try:
            self.logger.info("Running container with config: %s", container_config)
            container = self.client.containers.run(**container_config)
            self.logger.info("Running sidecar with config: %s", sidecar_config)
            sidecar = self.client.containers.run(**sidecar_config)
            return DockerContainer(
                container=container,
                logger=self.logger,
            ), DockerContainer(
                container=sidecar,
                logger=self.logger,
            )
        except ImageNotFound:
            self.logger.error(f"Image {self.image_name}:{self.image_tag} not found")
            raise

    def wait_for_container_stop(
        self,
        container: Optional[DockerContainer],
        main_container_status: Optional[dict[str, Any]] = None,
    ) -> Optional[dict]:
        """Wait for the container to stop and return its exit status.

        Args:
            container (DockerContainer): Container to wait for

        Returns:
            Optional[dict]:
                Container exit status containing 'StatusCode' and 'Error' if any
        """
        if not container:
            return None
        return container.wait_until_stop(main_container_status)
