import ast
import json
import logging
import os
import uuid
from typing import Any, Optional

from dotenv import load_dotenv
from unstract.worker.constants import Env, LogType, ToolKey

import docker
from docker import DockerClient  # type: ignore[attr-defined]
from unstract.core.pubsub_helper import LogPublisher

load_dotenv()

logger = logging.getLogger(__name__)


class UnstractWorker:
    def __init__(self, image_name: str, image_tag: str) -> None:
        self.image_name = image_name
        # If no image_tag is provided will assume the `latest` tag
        self.image_tag = image_tag or "latest"
        # Create a Docker client that communicates with
        #   the Docker daemon in the host environment
        self.client: DockerClient = docker.from_env()  # type: ignore[attr-defined]  # noqa: E501

        private_registry_credential_path = os.getenv(
            Env.PRIVATE_REGISTRY_CREDENTIAL_PATH
        )
        private_registry_username = os.getenv(Env.PRIVATE_REGISTRY_USERNAME)
        private_registry_url = os.getenv(Env.PRIVATE_REGISTRY_URL)
        if (
            private_registry_credential_path
            and private_registry_username
            and private_registry_url
        ):
            try:
                with open(private_registry_credential_path, encoding="utf-8") as file:
                    password = file.read()
                self.client.login(
                    username=private_registry_username,
                    password=password,
                    registry=private_registry_url,
                )
            except FileNotFoundError as file_err:
                logger.error(
                    f"Service account key file is not mounted "
                    f"in {private_registry_credential_path}: {file_err}"
                    "Logging to private registry might fail, if private tool is used."
                )

        self.image = self._get_image()

    def _get_image(self) -> str:
        """Will check if image exists locally and pulls the image using
        `self.image_name` and `self.image_tag` if necessary.

        Returns:
            str: image string combining repo name and tag like `ubuntu:22.04`
        """
        image_name_with_tag = f"{self.image_name}:{self.image_tag}"
        if self._image_exists(image_name_with_tag):
            return image_name_with_tag

        logger.info("Pulling the container: %s", image_name_with_tag)
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
            logger.info(
                "CONTAINER PULL STATUS: %s - %s : %s",
                line.get("status"),
                line.get("id"),
                line.get("progress"),
            )
        logger.info("Finished pulling the container: %s", image_name_with_tag)

        return image_name_with_tag

    def _image_exists(self, image_name_with_tag: str) -> bool:
        """Check if the container image exists in system.

        Args:
            image_name_with_tag (str): The image name with tag.

        Returns:
            bool: True if the image exists, False otherwise.
        """

        try:
            # Attempt to get the image information
            self.client.images.get(image_name_with_tag)
            logger.info(f"Image '{image_name_with_tag}' found in the local system.")
            return True
        except docker.errors.ImageNotFound:  # type: ignore[attr-defined]
            logger.info(f"Image '{image_name_with_tag}' not found in the local system.")
            return False
        except docker.errors.APIError as e:  # type: ignore[attr-defined]
            logger.error(f"An API error occurred: {e}")
            return False

    def normalize_container_name(self, name: str) -> str:
        return name.replace("/", "-") + "-" + str(uuid.uuid4())

    # Function to stream logs
    def stream_logs(
        self,
        container: Any,
        tool_instance_id: str,
        channel: Optional[str] = None,
    ) -> None:
        for line in container.logs(stream=True, follow=True):
            log_message = line.decode().strip()
            logger.info(f"Log message: {log_message}")
            self.process_log_message(
                log_message=log_message,
                tool_instance_id=tool_instance_id,
                channel=channel,
            )

    def get_valid_log_message(
        self, log_message: str, channel: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        try:
            log_dict = json.loads(log_message)
            if not isinstance(log_dict, dict):
                logger.error(f"Received invalid log: {log_dict}")
            else:
                return log_dict
        except json.JSONDecodeError as e:
            logger.warn(
                f"Received invalid JSON log message: {log_message} \n " f"error: {e}"
            )
        return None

    def process_log_message(
        self,
        log_message: str,
        tool_instance_id: str,
        channel: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        log_dict = self.get_valid_log_message(log_message, channel)
        if not log_dict:
            return None
        log_type = self.get_log_type(log_dict)
        if not self.is_valid_log_type(log_type):
            logger.warning(
                f"Received invalid logType: {log_type} with log message: " f"{log_dict}"
            )
            return None
        if log_type == LogType.RESULT:
            return log_dict
        if log_type == LogType.UPDATE:
            log_dict["component"] = tool_instance_id
        if channel:
            # Publish to channel of socket io
            LogPublisher.publish(channel, log_dict)
        return None

    def is_valid_log_type(self, log_type: Optional[str]) -> bool:
        if log_type in {
            LogType.LOG,
            LogType.UPDATE,
            LogType.COST,
            LogType.RESULT,
            LogType.SINGLE_STEP,
        }:
            return True
        return False

    def get_log_type(self, log_dict: Any) -> Optional[str]:
        if isinstance(log_dict, dict):
            log_type: Optional[str] = log_dict.get("type")
            return log_type
        return None

    def get_spec(self) -> Optional[Any]:
        self.container_name = self.normalize_container_name(self.image_name)
        container_config = {
            "name": self.container_name,
            "image": self.image,
            "command": ["--command", "SPEC"],
            "detach": True,
            "stream": True,
            "auto_remove": True,
            "stderr": True,
            "stdout": True,
        }
        logger.info(f"Docker config: {container_config}")

        # Run the Docker container
        try:
            container = self.client.containers.run(**container_config)
            for line in container.logs(stream=True):
                text = line.decode().strip()
                logger.info(text)
                if '"type": "SPEC"' in text:
                    return json.loads(text)
        except Exception as e:
            logger.error(f"Failed to run docker container: {e}")
        return None

    def get_properties(self) -> Optional[Any]:
        self.container_name = self.normalize_container_name(self.image_name)
        container_config = {
            "name": self.container_name,
            "image": self.image,
            "command": ["--command", "PROPERTIES"],
            "detach": True,
            "stream": True,
            "auto_remove": True,
            "stderr": True,
            "stdout": True,
        }
        logger.info(f"Docker config: {container_config}")

        # Run the Docker container
        try:
            container = self.client.containers.run(**container_config)
            for line in container.logs(stream=True):
                text = line.decode().strip()
                logger.info(text)
                if '"type": "PROPERTIES"' in text:
                    return json.loads(text)
        except Exception as e:
            logger.error(f"Failed to run docker container: {e}")
        return None

    def get_icon(self) -> Optional[Any]:
        self.container_name = self.normalize_container_name(self.image_name)
        container_config = {
            "name": self.container_name,
            "image": self.image,
            "command": ["--command", "ICON"],
            "detach": True,
            "stream": True,
            "auto_remove": True,
            "stderr": True,
            "stdout": True,
        }
        logger.info(f"Docker config: {container_config}")

        # Run the Docker container
        try:
            container = self.client.containers.run(**container_config)
            for line in container.logs(stream=True):
                text = line.decode().strip()
                logger.info(text)
                if '"type": "ICON"' in text:
                    return json.loads(text)
        except Exception as e:
            logger.error(f"Failed to run docker container: {e}")
        return None

    def get_variables(self) -> Optional[Any]:
        self.container_name = self.normalize_container_name(self.image_name)
        container_config = {
            "name": self.container_name,
            "image": self.image,
            "command": ["--command", "VARIABLES"],
            "detach": True,
            "stream": True,
            "auto_remove": True,
            "stderr": True,
            "stdout": True,
        }
        logger.info(f"Docker config: {container_config}")

        # Run the Docker container
        try:
            container = self.client.containers.run(**container_config)
            for line in container.logs(stream=True):
                text = line.decode().strip()
                logger.info(text)
                if '"type": "VARIABLES"' in text:
                    return json.loads(text)
        except Exception as e:
            logger.error(f"Failed to run docker container: {e}")
        return None

    def run_container(
        self,
        organization_id: str,
        workflow_id: str,
        execution_id: str,
        settings: dict[str, Any],
        envs: dict[str, Any],
        messaging_channel: Optional[str] = None,
    ) -> Optional[Any]:
        """RUN container With RUN Command.

        Args:
            workflow_id (str): projectId
            params (dict[str, Any]): params to run the tool
            settings (dict[str, Any]): Tool settings
            envs (dict[str, Any]): Tool env
            messaging_channel (Optional[str], optional): socket io channel

        Returns:
            Optional[Any]: _description_
        """
        tool_data_dir = os.environ.get(Env.TOOL_DATA_DIR, "/data")
        envs[Env.TOOL_DATA_DIR] = tool_data_dir
        self.organization_id = organization_id
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        self.params: dict[str, Any] = {}
        self.settings = settings
        self.envs = envs
        self.messaging_channel = messaging_channel
        self.container_name = (
            self.normalize_container_name(self.image_name) + "-" + self.workflow_id
        )
        container_config = self.get_container_run_config()
        # Add labels to container for logging with Loki.
        # This only required for observability.
        try:
            labels = ast.literal_eval(os.environ.get(Env.TOOL_CONTAINER_LABELS, ""))
            container_config["labels"] = labels
        except Exception as e:
            logger.info(f"Invalid labels for logging: {e}")

        logger.info(f"Docker config: {container_config}")

        # Run the Docker container
        container = None
        result = {"type": "RESULT", "result": None}
        try:
            container = self.client.containers.run(**container_config)
            tool_instance_id = str(self.settings.get(ToolKey.TOOL_INSTANCE_ID))
            # Stream logs
            self.stream_logs(
                container=container,
                tool_instance_id=tool_instance_id,
                channel=self.messaging_channel,
            )
        except Exception as e:
            logger.error(f"Failed to run docker container: {e}")
            result = {"type": "RESULT", "result": None, "error": str(e)}
        if container:
            self._cleanup_container(container)
        return result

    def get_container_run_config(self) -> dict[str, Any]:
        return {
            "name": self.container_name,
            "image": self.image,
            "command": [
                "--command",
                "RUN",
                "--settings",
                json.dumps(self.settings),
                "--log-level",
                "DEBUG",
            ],
            "detach": True,
            "stream": True,
            "auto_remove": False,
            "environment": self.envs,
            "stderr": True,
            "stdout": True,
            "network": os.environ.get(Env.TOOL_CONTAINER_NETWORK, ""),
            "mounts": [
                {
                    "type": "bind",
                    "source": os.path.join(
                        os.environ.get(Env.WORKFLOW_DATA_DIR, ""),
                        self.organization_id,
                        self.workflow_id,
                        self.execution_id,
                    ),
                    "target": os.environ.get(Env.TOOL_DATA_DIR, "/data"),
                }
            ],
        }

    def _cleanup_container(self, container: Any) -> None:
        try:
            container.remove(force=True)
        except Exception as remove_error:
            logger.error(f"Failed to remove docker container: {remove_error}")
