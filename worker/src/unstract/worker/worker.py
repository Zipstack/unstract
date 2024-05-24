import ast
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from docker.errors import APIError
from dotenv import load_dotenv
from flask import Flask
from unstract.worker.constants import Env, LogType, ToolKey
from unstract.worker.utils import Utils

import docker
from docker import DockerClient  # type: ignore[attr-defined]
from unstract.core.constants import LogFieldName
from unstract.core.pubsub_helper import LogPublisher

load_dotenv()


class UnstractWorker:
    def __init__(self, image_name: str, image_tag: str, app: Flask) -> None:
        self.image_name = image_name
        # If no image_tag is provided will assume the `latest` tag
        self.image_tag = image_tag or "latest"
        self.logger = app.logger
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
            self.logger.info(
                f"Image '{image_name_with_tag}' found in the local system."
            )
            return True
        except docker.errors.ImageNotFound:  # type: ignore[attr-defined]
            self.logger.info(
                f"Image '{image_name_with_tag}' not found in the local system."
            )
            return False
        except docker.errors.APIError as e:  # type: ignore[attr-defined]
            self.logger.error(f"An API error occurred: {e}")
            return False

    def normalize_container_name(self, name: str) -> str:
        return name.replace("/", "-") + "-" + str(uuid.uuid4())

    # Function to stream logs
    def stream_logs(
        self,
        container: Any,
        tool_instance_id: str,
        execution_id: str,
        organization_id: str,
        channel: Optional[str] = None,
    ) -> None:
        for line in container.logs(stream=True, follow=True):
            log_message = line.decode().strip()
            self.logger.info(f"[{self.container_name}] - {log_message}")
            self.process_log_message(
                log_message=log_message,
                tool_instance_id=tool_instance_id,
                channel=channel,
                execution_id=execution_id,
                organization_id=organization_id,
            )

    def get_valid_log_message(self, log_message: str) -> Optional[dict[str, Any]]:
        """Get a valid log message from the log message.

        Args:
            log_message (str): str

        Returns:
            Optional[dict[str, Any]]: json message
        """
        try:
            log_dict = json.loads(log_message)
            if isinstance(log_dict, dict):
                return log_dict
        except json.JSONDecodeError:
            return None

    def process_log_message(
        self,
        log_message: str,
        tool_instance_id: str,
        execution_id: str,
        organization_id: str,
        channel: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        log_dict = self.get_valid_log_message(log_message)
        if not log_dict:
            return None
        log_type = self.get_log_type(log_dict)
        if not self.is_valid_log_type(log_type):
            self.logger.warning(
                f"Received invalid logType: {log_type} with log message: {log_dict}"
            )
            return None
        if log_type == LogType.RESULT:
            return log_dict
        if log_type == LogType.UPDATE:
            log_dict["component"] = tool_instance_id
        if channel:
            log_dict[LogFieldName.EXECUTION_ID] = execution_id
            log_dict[LogFieldName.ORGANIZATION_ID] = organization_id
            log_dict[LogFieldName.TIMESTAMP] = datetime.now(timezone.utc).timestamp()

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
        self.logger.info(f"Docker config: {container_config}")

        # Run the Docker container
        try:
            container = self.client.containers.run(**container_config)
            for line in container.logs(stream=True):
                text = line.decode().strip()
                self.logger.info(text)
                if '"type": "SPEC"' in text:
                    return json.loads(text)
        except Exception as e:
            self.logger.error(f"Failed to run docker container: {e}")
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
        self.logger.info(f"Docker config: {container_config}")

        # Run the Docker container
        try:
            container = self.client.containers.run(**container_config)
            for line in container.logs(stream=True):
                text = line.decode().strip()
                self.logger.info(text)
                if '"type": "PROPERTIES"' in text:
                    return json.loads(text)
        except Exception as e:
            self.logger.error(f"Failed to run docker container: {e}")
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
        self.logger.info(f"Docker config: {container_config}")

        # Run the Docker container
        try:
            container = self.client.containers.run(**container_config)
            for line in container.logs(stream=True):
                text = line.decode().strip()
                self.logger.info(text)
                if '"type": "ICON"' in text:
                    return json.loads(text)
        except Exception as e:
            self.logger.error(f"Failed to run docker container: {e}")
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
        self.logger.info(f"Docker config: {container_config}")

        # Run the Docker container
        try:
            container = self.client.containers.run(**container_config)
            for line in container.logs(stream=True):
                text = line.decode().strip()
                self.logger.info(text)
                if '"type": "VARIABLES"' in text:
                    return json.loads(text)
        except Exception as e:
            self.logger.error(f"Failed to run docker container: {e}")
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
        remove_container_on_exit = Utils.remove_container_on_exit()
        # Add labels to container for logging with Loki.
        # This only required for observability.
        try:
            labels = ast.literal_eval(os.environ.get(Env.TOOL_CONTAINER_LABELS, ""))
            container_config["labels"] = labels
        except Exception as e:
            self.logger.info(f"Invalid labels for logging: {e}")

        self.logger.info(f"Docker config: {container_config}")

        # Run the Docker container
        container = None
        result = {"type": "RESULT", "result": None}
        try:
            container = self.client.containers.run(**container_config)
            self.logger.info(f"Running Docker container: {self.container_name}")
            tool_instance_id = str(self.settings.get(ToolKey.TOOL_INSTANCE_ID))
            # Stream logs
            self.stream_logs(
                container=container,
                tool_instance_id=tool_instance_id,
                channel=self.messaging_channel,
                execution_id=execution_id,
                organization_id=organization_id,
            )
        except Exception as e:
            self.logger.error(f"Failed to run docker container: {e}")
            result = {"type": "RESULT", "result": None, "error": str(e)}
        if container and remove_container_on_exit:
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
            self.logger.error(f"Failed to remove docker container: {remove_error}")
