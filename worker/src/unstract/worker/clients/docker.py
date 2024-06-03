import logging
import os
from typing import Any

from docker.errors import APIError, ImageNotFound
from docker.models.containers import Container
from unstract.worker.constants import Env

from docker import DockerClient, from_env

from .interface import ContainerClientInterface


class Client(ContainerClientInterface):
    def __init__(self, image_name: str, image_tag: str, logger: logging.Logger) -> None:
        self.image_name = image_name
        # If no image_tag is provided will assume the `latest` tag
        self.image_tag = image_tag or "latest"
        self.logger = logger

        # Create a Docker client that communicates with
        #   the Docker daemon in the host environment
        self.client: DockerClient = from_env()
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

    def get_image(self) -> str:
        """Will check if image exists locally and pulls the image using
        `self.image_name` and `self.image_tag` if necessary.

        Returns:
            str: image string combining repo name and tag like `ubuntu:22.04`
        """
        image_name_with_tag = f"{self.image_name}:{self.image_tag}"
        if self.__image_exists(image_name_with_tag):
            return image_name_with_tag

        self.logger.info("Pulling the container: %s", image_name_with_tag)
        resp = self.client.api.pull(
            repository=self.image_name,
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

    def run_container(self, config: dict[Any, Any]) -> Container:
        return self.client.containers.run(**config)
