import ast
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv
from flask import Flask
from unstract.worker.clients.helper import ContainerClientHelper
from unstract.worker.clients.interface import (
    ContainerClientInterface,
    ContainerInterface,
)
from unstract.worker.constants import Env, FeatureFlag, LogLevel, LogType, ToolKey
from unstract.worker.exception import ToolRunException

from unstract.core.constants import LogFieldName
from unstract.core.pubsub_helper import LogPublisher
from unstract.flags.feature_flag import check_feature_flag_status

load_dotenv()
# Loads the container clinet class.
client_class = ContainerClientHelper.get_container_client()


class UnstractWorker:
    def __init__(self, image_name: str, image_tag: str, app: Flask) -> None:
        self.image_name = image_name
        # If no image_tag is provided will assume the `latest` tag
        self.image_tag = image_tag or "latest"
        self.logger = app.logger
        self.client: ContainerClientInterface = client_class(
            self.image_name, self.image_tag, self.logger
        )

    # Function to stream logs
    def stream_logs(
        self,
        container: ContainerInterface,
        tool_instance_id: str,
        execution_id: str,
        organization_id: str,
        channel: Optional[str] = None,
    ) -> None:
        for line in container.logs(follow=True):
            log_message = line
            self.logger.debug(f"[{container.name}] - {log_message}")
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
        log_level = self.get_log_level(log_dict)
        if log_type == LogType.LOG and log_level == LogLevel.ERROR:
            raise ToolRunException(log_dict.get("log"))
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

    def get_log_level(self, log_dict: Any) -> Optional[str]:
        if isinstance(log_dict, dict):
            log_level: Optional[str] = log_dict.get("level")
            return log_level
        return None

    def run_command(self, command: str) -> Optional[Any]:
        """Runs any given command on the container.

        Args:
            command (str): Command to be executed.

        Returns:
            Optional[Any]: Response from container or None if error occures.
        """
        command = command.upper()
        container_config = self.client.get_container_run_config(
            command=["--command", command],
            organization_id="",
            workflow_id="",
            execution_id="",
            run_id="",
            auto_remove=True,
        )
        container = None

        # Run the Docker container
        try:
            container: ContainerInterface = self.client.run_container(container_config)
            for text in container.logs(follow=True):
                self.logger.info(f"[{container.name}] - {text}")
                if f'"type": "{command}"' in text:
                    return json.loads(text)
        except Exception as e:
            self.logger.error(
                f"Failed to run docker container: {e}", stack_info=True, exc_info=True
            )
        if container:
            container.cleanup()
        return None

    def run_container(
        self,
        organization_id: str,
        workflow_id: str,
        execution_id: str,
        run_id: str,
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
        tool_data_dir = os.getenv(Env.TOOL_DATA_DIR, "/data")
        if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):
            envs[Env.EXECUTION_DATA_DIR] = os.path.join(
                os.getenv(Env.WORKFLOW_EXECUTION_DIR_PREFIX, ""),
                organization_id,
                workflow_id,
                execution_id,
            )
            envs[Env.WORKFLOW_EXECUTION_FILE_STORAGE_CREDENTIALS] = os.getenv(
                Env.WORKFLOW_EXECUTION_FILE_STORAGE_CREDENTIALS, "{}"
            )
        else:
            envs[Env.TOOL_DATA_DIR] = tool_data_dir

        container_config = self.client.get_container_run_config(
            command=[
                "--command",
                "RUN",
                "--settings",
                json.dumps(settings),
                "--log-level",
                "DEBUG",
            ],
            organization_id=organization_id,
            workflow_id=workflow_id,
            execution_id=execution_id,
            run_id=run_id,
            envs=envs,
        )
        # Add labels to container for logging with Loki.
        # This only required for observability.
        try:
            labels = ast.literal_eval(os.getenv(Env.TOOL_CONTAINER_LABELS, "[]"))
            container_config["labels"] = labels
        except Exception as e:
            self.logger.info(f"Invalid labels for logging: {e}")

        # Run the Docker container
        container = None
        result = {"type": "RESULT", "result": None}
        try:
            self.logger.info(
                f"Execution ID: {execution_id}, running docker "
                f"container: {container_config.get('name')}"
            )
            container: ContainerInterface = self.client.run_container(container_config)
            tool_instance_id = str(settings.get(ToolKey.TOOL_INSTANCE_ID))
            # Stream logs
            self.stream_logs(
                container=container,
                tool_instance_id=tool_instance_id,
                channel=messaging_channel,
                execution_id=execution_id,
                organization_id=organization_id,
            )
        except ToolRunException as te:
            self.logger.error(
                "Error while running docker container"
                f" {container_config.get('name')}: {te}",
                stack_info=True,
                exc_info=True,
            )
            result = {"type": "RESULT", "result": None, "error": str(te.message)}
        except Exception as e:
            self.logger.error(
                f"Failed to run docker container: {e}", stack_info=True, exc_info=True
            )
            result = {"type": "RESULT", "result": None, "error": str(e)}
        if container:
            container.cleanup()
        return result
