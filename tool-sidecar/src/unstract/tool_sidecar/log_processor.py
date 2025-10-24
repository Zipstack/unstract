"""Sidecar container implementation for log processing and result handling.
This sidecar runs alongside the tool container in the same pod, monitoring
the tool's output log file and streaming logs to Redis while watching for
completion signals.
"""

import json
import logging
import os
import signal
import time
from datetime import UTC, datetime
from typing import Any

from unstract.core.constants import LogFieldName
from unstract.core.pubsub_helper import LogPublisher
from unstract.core.tool_execution_status import (
    ToolExecutionData,
    ToolExecutionStatus,
    ToolExecutionTracker,
)
from unstract.core.utilities import redact_sensitive_string

from .constants import Env, LogLevel, LogType
from .dto import LogLineDTO

logger = logging.getLogger(__name__)

# Global shutdown flag for graceful termination
_shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    signal_name = signal.Signals(signum).name
    logger.info(f"Received {signal_name}, initiating graceful shutdown...")
    _shutdown_requested = True


class LogProcessor:
    def __init__(
        self,
        log_path: str,
        redis_host: str,
        redis_port: str,
        redis_user: str,
        redis_password: str,
        tool_instance_id: str,
        execution_id: str,
        organization_id: str,
        file_execution_id: str,
        messaging_channel: str,
        container_name: str = "",
    ):
        """Initialize the log processor with necessary connections and paths.

        Args:
            log_path: Path to the log file to monitor
            redis_url: URL for Redis connection
            tool_instance_id: ID of the tool instance
            execution_id: ID of the execution
            organization_id: ID of the organization
            file_execution_id: ID of the file execution
        """
        self.log_path = log_path
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_user = redis_user
        self.redis_password = redis_password
        self.tool_instance_id = tool_instance_id
        self.execution_id = execution_id
        self.organization_id = organization_id
        self.file_execution_id = file_execution_id
        self.messaging_channel = messaging_channel
        self.container_name = container_name
        self.tool_execution_tracker = ToolExecutionTracker()
        self._update_tool_execution_status(status=ToolExecutionStatus.RUNNING)

    def _update_tool_execution_status(
        self, status: ToolExecutionStatus, error: str | None = None
    ) -> None:
        try:
            tool_execution_data = ToolExecutionData(
                execution_id=self.execution_id,
                tool_instance_id=self.tool_instance_id,
                file_execution_id=self.file_execution_id,
                organization_id=self.organization_id,
                status=status,
                error=error,
            )
            self.tool_execution_tracker.update_status(
                tool_execution_data=tool_execution_data
            )
        except Exception as e:
            logger.error(f"Failed to update tool execution status: {e}", exc_info=True)

    def wait_for_log_file(self, timeout: int = 300) -> bool:
        """Wait for the log file to be created by the tool container.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            bool: True if file exists, False if timeout occurred
        """
        start_time = time.time()
        while not os.path.exists(self.log_path):
            if time.time() - start_time > timeout:
                return False
            time.sleep(0.1)
        return True

    def process_log_line(self, line: str) -> LogLineDTO:
        """Process a single log line, checking for completion signal.

        Args:
            line: Log line to process

        Returns:
            Optional[Dict]: Parsed JSON if line is a completion signal
        """
        # Stream log to Redis
        if LogFieldName.TOOL_TERMINATION_MARKER in line:
            logger.info(
                "Tool container terminated with status "
                f"{LogFieldName.TOOL_TERMINATION_MARKER}"
            )
            return LogLineDTO(is_terminated=True)

        log_dict = self.get_valid_log_message(line)
        if not log_dict:
            logger.info(f"{line}")
            return LogLineDTO()

        log_type = log_dict.get("type")
        log_level = log_dict.get("level")
        if not self.is_valid_log_type(log_type):
            logger.warning(
                f"Received invalid logType: {log_type} with log message: {log_dict}"
            )
            return LogLineDTO()

        log_process_status = LogLineDTO()
        if log_type == LogType.LOG:
            if log_level == LogLevel.ERROR:
                logger.error(f"{log_dict.get('log')}")
                log_process_status.error = log_dict.get("log")
                self._update_tool_execution_status(
                    status=ToolExecutionStatus.FAILED, error=log_dict.get("log")
                )
            else:
                logger.info(f"{log_dict.get('log')}")
        elif log_type == LogType.RESULT:
            logger.info(f"Tool '{self.container_name}' completed running")
            self._update_tool_execution_status(status=ToolExecutionStatus.SUCCESS)
            return LogLineDTO(with_result=True)
        elif log_type == LogType.UPDATE:
            logger.info("Pushing UI updates")
            log_dict["component"] = self.tool_instance_id

        log_dict[LogFieldName.EXECUTION_ID] = self.execution_id
        log_dict[LogFieldName.ORGANIZATION_ID] = self.organization_id
        log_dict[LogFieldName.TIMESTAMP] = self.get_log_timestamp(log_dict)
        log_dict[LogFieldName.FILE_EXECUTION_ID] = self.file_execution_id
        # Publish to channel of socket io
        LogPublisher.publish(self.messaging_channel, log_dict)
        return log_process_status

    def get_log_timestamp(self, log_dict: dict[str, Any]) -> float:
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

    def monitor_logs(self) -> None:
        """Main loop to monitor log file for new content and completion signals.
        Uses file polling with position tracking to efficiently read new lines.
        Handles graceful shutdown via SIGTERM.
        """
        global _shutdown_requested
        logger.info("Starting log monitoring...")
        if not self.wait_for_log_file():
            raise TimeoutError("Log file was not created within timeout period")

        # Monitor the file for new content
        with open(self.log_path) as f:
            while True:
                # Check for shutdown signal
                if _shutdown_requested:
                    logger.info("Shutdown requested, performing final log collection...")
                    self._final_log_collection(f)
                    break

                # Remember current position
                where = f.tell()
                line = f.readline()

                if not line:
                    # No new data, check if tool container is done
                    if os.path.exists(
                        os.path.join(os.path.dirname(self.log_path), "completed")
                    ):
                        break

                    # Sleep briefly to avoid CPU spinning
                    time.sleep(0.1)
                    # Go back to where we were
                    f.seek(where)
                    continue

                # Process the log line
                log_line = self.process_log_line(line)
                if log_line.is_terminated:
                    logger.info("Completion signal received")
                    break

        logger.info("Log monitoring completed")

    def _final_log_collection(self, file_handle) -> None:
        """Perform final collection of any remaining logs before shutdown."""
        logger.info("Performing final log collection...")

        # Give main container brief moment to write final logs
        time.sleep(0.2)

        lines_collected = 0

        # Read any remaining lines in the file
        while True:
            line = file_handle.readline()
            if not line:
                break

            lines_collected += 1
            log_line = self.process_log_line(line.strip())

            if log_line.is_terminated:
                logger.info("Found completion signal during final collection")

        logger.info(
            f"Final log collection completed, processed {lines_collected} remaining lines"
        )


def main():
    """Main entry point for the sidecar container.
    Sets up the log processor with environment variables and starts monitoring.
    """
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    logger.info("Signal handlers registered for graceful shutdown")

    # Get configuration from environment
    log_path = os.getenv(Env.LOG_PATH, "/shared/logs/logs.txt")
    redis_host = os.getenv(Env.REDIS_HOST)
    redis_port = os.getenv(Env.REDIS_PORT)
    redis_user = os.getenv(Env.REDIS_USER)
    redis_password = os.getenv(Env.REDIS_PASSWORD)
    # Needed for Kombu (used from unstract-core)
    celery_broker_base_url = os.getenv(Env.CELERY_BROKER_BASE_URL)
    celery_broker_user = os.getenv(Env.CELERY_BROKER_USER)
    celery_broker_pass = os.getenv(Env.CELERY_BROKER_PASS, "")

    # Get execution parameters from environment
    tool_instance_id = os.getenv(Env.TOOL_INSTANCE_ID)
    execution_id = os.getenv(Env.EXECUTION_ID)
    organization_id = os.getenv(Env.ORGANIZATION_ID)
    file_execution_id = os.getenv(Env.FILE_EXECUTION_ID)
    messaging_channel = os.getenv(Env.MESSAGING_CHANNEL)
    container_name = os.getenv(Env.CONTAINER_NAME)

    # Validate required parameters
    required_params = {
        Env.TOOL_INSTANCE_ID: tool_instance_id,
        Env.EXECUTION_ID: execution_id,
        Env.ORGANIZATION_ID: organization_id,
        Env.FILE_EXECUTION_ID: file_execution_id,
        Env.MESSAGING_CHANNEL: messaging_channel,
        Env.LOG_PATH: log_path,
        Env.REDIS_HOST: redis_host,
        Env.REDIS_PORT: redis_port,
        Env.CELERY_BROKER_BASE_URL: celery_broker_base_url,
        Env.CELERY_BROKER_USER: celery_broker_user,
        Env.CELERY_BROKER_PASS: redact_sensitive_string(celery_broker_pass),
    }

    logger.info(f"Log processor started with params: {required_params}")

    missing_params = [k for k, v in required_params.items() if not v]
    if missing_params:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_params)}"
        )

    # Create and run log processor
    processor = LogProcessor(
        log_path=log_path,
        redis_host=redis_host,
        redis_port=redis_port,
        redis_user=redis_user,
        redis_password=redis_password,
        messaging_channel=messaging_channel,
        tool_instance_id=tool_instance_id,
        execution_id=execution_id,
        organization_id=organization_id,
        file_execution_id=file_execution_id,
        container_name=container_name,
    )
    processor.monitor_logs()


if __name__ == "__main__":
    main()
