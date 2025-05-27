import ast
import json
import os
from datetime import UTC, datetime
from typing import Any

from dotenv import load_dotenv
from flask import Flask

from unstract.core.constants import LogFieldName
from unstract.core.pubsub_helper import LogPublisher
from unstract.runner.clients.helper import ContainerClientHelper
from unstract.runner.clients.interface import (
    ContainerClientInterface,
    ContainerInterface,
)
from unstract.runner.constants import Env, LogLevel, LogType, ToolKey
from unstract.runner.exception import ToolRunException
from unstract.runner.utils import Utils

load_dotenv()
# Loads the container client class.
client_class = ContainerClientHelper.get_container_client()


class UnstractRunner:
    def __init__(self, image_name: str, image_tag: str, app: Flask) -> None:
        self.image_name = image_name
        # If no image_tag is provided will assume the `latest` tag
        self.image_tag = image_tag or "latest"
        self.logger = app.logger
        self.sidecar_enabled = Utils.is_sidecar_enabled()
        self.client: ContainerClientInterface = client_class(
            self.image_name, self.image_tag, self.logger, self.sidecar_enabled
        )

    # Function to stream logs
    def stream_logs(
        self,
        container: ContainerInterface,
        tool_instance_id: str,
        execution_id: str,
        organization_id: str,
        file_execution_id: str,
        container_name: str,
        channel: str | None = None,
    ) -> None:
        for line in container.logs(follow=True):
            log_message = line
            self.process_log_message(
                log_message=log_message,
                tool_instance_id=tool_instance_id,
                channel=channel,
                execution_id=execution_id,
                organization_id=organization_id,
                file_execution_id=file_execution_id,
                container_name=container_name,
            )

    def get_valid_log_message(self, log_message: str) -> dict[str, Any] | None:
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
        file_execution_id: str,
        container_name: str,
        channel: str | None = None,
    ) -> dict[str, Any] | None:
        log_dict = self.get_valid_log_message(log_message)
        if not log_dict:
            self.logger.debug(f"[{container_name}] {log_message}")
            return None
        log_type = log_dict.get("type")
        log_level = log_dict.get("level")

        if not self.is_valid_log_type(log_type):
            self.logger.warning(
                f"Received invalid logType: {log_type} with log message: {log_dict}"
            )
            return None

        if log_type == LogType.LOG:
            if log_level == LogLevel.ERROR:
                raise ToolRunException(log_dict.get("log"))
            self.logger.debug(f"[{container_name}] {log_message}")
        elif log_type == LogType.RESULT:
            self.logger.debug(f"[{container_name}] Completed running")
            return log_dict
        elif log_type == LogType.UPDATE:
            self.logger.debug(f"[{container_name}] Pushing UI updates")
            log_dict["component"] = tool_instance_id
        if channel:
            log_dict[LogFieldName.EXECUTION_ID] = execution_id
            log_dict[LogFieldName.ORGANIZATION_ID] = organization_id
            log_dict[LogFieldName.TIMESTAMP] = self._get_log_timestamp(log_dict)
            log_dict[LogFieldName.FILE_EXECUTION_ID] = file_execution_id

            # Publish to channel of socket io
            LogPublisher.publish(channel, log_dict)
        return None

    def is_valid_log_type(self, log_type: str | None) -> bool:
        if log_type in {
            LogType.LOG,
            LogType.UPDATE,
            LogType.COST,
            LogType.RESULT,
            LogType.SINGLE_STEP,
        }:
            return True
        return False

    def _get_log_timestamp(self, log_dict: dict[str, Any]) -> float:
        """Obtains the timestamp from the log dictionary.

        Checks if the log dictionary has an `emitted_at` key and returns the
        corresponding timestamp. If the key is not present, returns the current
        timestamp.

        Args:
            log_dict (dict[str, Any]): Log message from tool

        Returns:
            float: Timestamp of the log message
        """
        # Use current timestamp if emitted_at is not present
        if "emitted_at" not in log_dict:
            return datetime.now(UTC).timestamp()

        emitted_at = log_dict["emitted_at"]
        if isinstance(emitted_at, str):
            # Convert ISO format string to UNIX timestamp
            return datetime.fromisoformat(emitted_at).timestamp()
        elif isinstance(emitted_at, (int, float)):
            # Already a UNIX timestamp
            return float(emitted_at)

    def _parse_additional_envs(self) -> dict[str, Any]:
        """Parse TOOL_ADDITIONAL_ENVS environment variable to get additional
        environment variables.
        Also propagates OpenTelemetry trace context if available.

        Returns:
            dict: Dictionary containing parsed environment variables
                  or empty dict if none found.
        """
        additional_envs: dict[str, Any] = {}

        # Get additional envs from environment variable
        tool_additional_envs = os.getenv("TOOL_ADDITIONAL_ENVS")
        if not tool_additional_envs:
            return additional_envs
        try:
            additional_envs = json.loads(tool_additional_envs)
            self.logger.info(
                f"Parsed additional environment variables: {additional_envs}"
            )
        except json.JSONDecodeError as e:
            self.logger.warning(f"Failed to parse TOOL_ADDITIONAL_ENVS: {e}")

        # Propagate OpenTelemetry trace context if available
        # This is required only if additional envs are present
        try:
            from opentelemetry import trace

            current_span = trace.get_current_span()
            if current_span.is_recording():
                span_context = current_span.get_span_context()
                if span_context.is_valid:
                    # Add trace context to environment variables
                    additional_envs.update(
                        {
                            "OTEL_PROPAGATORS": "tracecontext",
                            "OTEL_TRACE_ID": f"{span_context.trace_id:032x}",
                            "OTEL_SPAN_ID": f"{span_context.span_id:016x}",
                            "OTEL_TRACE_FLAGS": f"{span_context.trace_flags:02x}",
                        }
                    )
                    self.logger.debug(
                        f"Propagating trace context: {span_context.trace_id:032x}"
                    )
        except Exception as e:
            # OpenTelemetry not available or error occurred, skip trace propagation
            self.logger.debug(f"Skipping trace propagation: {e}")

        return additional_envs

    def _get_sidecar_container_config(
        self,
        container_name: str,
        shared_log_dir: str,
        shared_log_file: str,
        file_execution_id: str,
        execution_id: str,
        organization_id: str,
        messaging_channel: str,
        tool_instance_id: str,
    ) -> dict[str, Any]:
        """Returns the container configuration for the sidecar container."""
        sidecar_env = {
            "LOG_PATH": shared_log_file,
            "REDIS_HOST": os.getenv(Env.REDIS_HOST),
            "REDIS_PORT": os.getenv(Env.REDIS_PORT),
            "REDIS_USER": os.getenv(Env.REDIS_USER),
            "REDIS_PASSWORD": os.getenv(Env.REDIS_PASSWORD),
            "TOOL_INSTANCE_ID": tool_instance_id,
            "EXECUTION_ID": execution_id,
            "ORGANIZATION_ID": organization_id,
            "FILE_EXECUTION_ID": file_execution_id,
            "MESSAGING_CHANNEL": messaging_channel,
            "LOG_LEVEL": os.getenv(Env.LOG_LEVEL, "INFO"),
            "CELERY_BROKER_URL": os.getenv(Env.CELERY_BROKER_URL),
            "CONTAINER_NAME": container_name,
        }
        sidecar_config = self.client.get_container_run_config(
            command=[],
            file_execution_id=file_execution_id,
            shared_log_dir=shared_log_dir,
            container_name=container_name,
            envs=sidecar_env,
            sidecar=True,
        )
        return sidecar_config

    def run_command(self, command: str) -> Any | None:
        """Runs any given command on the container.

        Args:
            command (str): Command to be executed.

        Returns:
            Optional[Any]: Response from container or None if error occures.
        """
        command = command.upper()

        # Get additional environment variables to pass to the container
        additional_env = self._parse_additional_envs()

        container_config = self.client.get_container_run_config(
            command=["--command", command],
            file_execution_id="",
            auto_remove=True,
            envs=additional_env,
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

    def _get_container_command(
        self, shared_log_dir: str, shared_log_file: str, settings: dict[str, Any]
    ):
        """Returns the container command to run the tool."""
        settings_json = json.dumps(settings).replace("'", "\\'")
        # Prepare the tool execution command
        tool_cmd = (
            f"opentelemetry-instrument python main.py --command RUN "
            f"--settings '{settings_json}' --log-level DEBUG"
        )

        if not self.sidecar_enabled:
            return tool_cmd

        # Shell script components
        mkdir_cmd = f"mkdir -p {shared_log_dir}"
        run_tool_fn = (
            "run_tool() { "
            f"{tool_cmd}; "
            "exit_code=$?; "
            f'echo "{LogFieldName.TOOL_TERMINATION_MARKER} with exit code $exit_code" '
            f">> {shared_log_file}; "
            "return $exit_code; "
            "}"
        )
        execute_cmd = f"run_tool > {shared_log_file} 2>&1"

        # Combine all commands
        shell_script = f"{mkdir_cmd} && {run_tool_fn}; {execute_cmd}"
        return shell_script

    def run_container(
        self,
        organization_id: str,
        workflow_id: str,
        execution_id: str,
        file_execution_id: str,
        settings: dict[str, Any],
        envs: dict[str, Any],
        container_name: str,
        messaging_channel: str | None = None,
    ) -> Any | None:
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
        envs[Env.EXECUTION_DATA_DIR] = os.path.join(
            os.getenv(Env.WORKFLOW_EXECUTION_DIR_PREFIX, ""),
            organization_id,
            workflow_id,
            execution_id,
            file_execution_id,
        )
        envs[Env.WORKFLOW_EXECUTION_FILE_STORAGE_CREDENTIALS] = os.getenv(
            Env.WORKFLOW_EXECUTION_FILE_STORAGE_CREDENTIALS, "{}"
        )

        # Get additional environment variables to pass to the container
        additional_env = self._parse_additional_envs()
        tool_instance_id = str(settings.get(ToolKey.TOOL_INSTANCE_ID))
        shared_log_dir = "/shared/logs"  # Mount directory, not file
        shared_log_file = os.path.join(shared_log_dir, "logs.txt")
        container_command = self._get_container_command(
            shared_log_dir=shared_log_dir,
            shared_log_file=shared_log_file,
            settings=settings,
        )

        container_config = self.client.get_container_run_config(
            command=["/bin/sh", "-c", container_command],
            file_execution_id=file_execution_id,
            shared_log_dir=shared_log_dir,  # Pass directory for mounting
            container_name=container_name,
            envs={**envs, **additional_env},
            organization_id=organization_id,
            workflow_id=workflow_id,
            execution_id=execution_id,
            messaging_channel=messaging_channel,
            tool_instance_id=tool_instance_id,
        )

        sidecar_config: dict[str, Any] | None = None
        if self.sidecar_enabled:
            sidecar_config = self._get_sidecar_container_config(
                container_name=container_name,
                shared_log_dir=shared_log_dir,
                shared_log_file=shared_log_file,
                file_execution_id=file_execution_id,
                execution_id=execution_id,
                organization_id=organization_id,
                messaging_channel=messaging_channel,
                tool_instance_id=tool_instance_id,
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
        sidecar = None
        result = {"type": "RESULT", "result": None}
        try:
            self.logger.info(
                f"Execution ID: {execution_id}, running docker "
                f"container: {container_name}"
            )
            if sidecar_config:
                containers: tuple[ContainerInterface, ContainerInterface | None] = (
                    self.client.run_container_with_sidecar(
                        container_config, sidecar_config
                    )
                )
                container, sidecar = containers
                status = self.client.wait_for_container_stop(container)
                self.logger.info(
                    f"Execution ID: {execution_id}, docker "
                    f"container: {container_name} ran with status: {status}"
                )
                self.client.wait_for_container_stop(sidecar, main_container_status=status)
                self.logger.info(
                    f"Execution ID: {execution_id}, docker "
                    f"container: {container_name} completed execution"
                )
            else:
                container: ContainerInterface = self.client.run_container(
                    container_config
                )
                self.logger.info(
                    f"Execution ID: {execution_id}, docker "
                    f"container: {container_name} streaming logs..."
                )
                # Stream logs
                self.stream_logs(
                    container=container,
                    tool_instance_id=tool_instance_id,
                    channel=messaging_channel,
                    execution_id=execution_id,
                    organization_id=organization_id,
                    file_execution_id=file_execution_id,
                    container_name=container_name,
                )
                self.logger.info(
                    f"Execution ID: {execution_id}, docker "
                    f"container: {container_name} ran successfully"
                )

        except ToolRunException as te:
            self.logger.error(
                f"Error while running docker container {container_config.get('name')}: {te}",
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
            container.cleanup(client=self.client)
        if sidecar:
            sidecar.cleanup(client=self.client)
        return result
