"""Worker Workflow Logger - WebSocket Log Publisher for Workers

This module provides WebSocket logging functionality for workers, matching
the backend's workflow_log.py functionality but adapted for the worker environment.

Usage:
    # Initialize logger
    workflow_logger = WorkerWorkflowLogger(
        execution_id=execution_id,
        log_stage=LogStage.PROCESSING,
        file_execution_id=file_execution_id,
        organization_id=organization_id
    )

    # Send logs to UI via WebSocket
    workflow_logger.log_info(logger, "Processing file batch...")
    workflow_logger.log_error(logger, "Failed to process file")
    workflow_logger.publish_update_log(LogState.RUNNING, "File processing started")
"""

import logging

from unstract.core.pubsub_helper import LogPublisher
from unstract.workflow_execution.enums import (
    LogComponent,
    LogLevel,
    LogStage,
    LogState,
)

from .logger import WorkerLogger

# Get worker logger for internal logging
logger = WorkerLogger.get_logger(__name__)


class WorkerWorkflowLogger:
    """Worker-compatible workflow logger that sends logs to UI via WebSocket.

    This mirrors the backend's WorkflowLog class but adapted for workers:
    - Uses worker StateStore equivalent
    - Compatible with worker environment variables
    - Maintains the same API for easy migration
    """

    def __init__(
        self,
        execution_id: str,
        log_stage: LogStage,
        file_execution_id: str | None = None,
        organization_id: str | None = None,
        pipeline_id: str | None = None,
        log_events_id: str | None = None,
    ):
        """Initialize workflow logger for worker environment.

        Args:
            execution_id: Workflow execution ID
            log_stage: Current processing stage (SOURCE, DESTINATION, PROCESSING, etc.)
            file_execution_id: Optional file execution ID for file-specific logs
            organization_id: Organization ID for message routing
            pipeline_id: Pipeline ID for message routing (fallback)
            log_events_id: Explicit log events ID (overrides other channel logic)
        """
        # Try to get log_events_id from worker StateStore if not provided
        if not log_events_id:
            try:
                # Try to import and use the worker's StateStore equivalent
                from ..context import StateStore

                log_events_id = StateStore.get("LOG_EVENTS_ID")
            except ImportError:
                logger.debug(
                    "StateStore not available in worker, using pipeline_id for messaging channel"
                )

        # Determine messaging channel (matches backend logic)
        self.messaging_channel = log_events_id if log_events_id else pipeline_id
        self.execution_id = str(execution_id)
        self.file_execution_id = str(file_execution_id) if file_execution_id else None
        self.organization_id = str(organization_id) if organization_id else None
        self.log_stage = log_stage

        if not self.messaging_channel:
            logger.warning(
                f"No messaging channel available for execution {execution_id}. "
                f"WebSocket logs may not be delivered to UI."
            )

    def publish_log(
        self,
        message: str,
        level: LogLevel = LogLevel.INFO,
        step: int | None = None,
        cost_type: str | None = None,
        cost_units: str | None = None,
        cost_value: float | None = None,
    ) -> None:
        """Publish a log message to the WebSocket channel.

        Args:
            message: Log message to display in UI
            level: Log level (INFO, ERROR)
            step: Optional step number for multi-step processes
            cost_type: Optional cost tracking type
            cost_units: Optional cost units
            cost_value: Optional cost value
        """
        try:
            if not self.messaging_channel:
                logger.warning(f"No messaging channel, skipping WebSocket log: {message}")
                return

            log_details = LogPublisher.log_workflow(
                stage=self.log_stage.value,
                message=message,
                level=level.value,
                step=step,
                execution_id=self.execution_id,
                file_execution_id=self.file_execution_id,
                organization_id=self.organization_id,
                cost_type=cost_type,
                cost_units=cost_units,
                cost_value=cost_value,
            )

            # Publish to WebSocket channel
            success = LogPublisher.publish(self.messaging_channel, log_details)
            if not success:
                logger.warning(f"Failed to publish WebSocket log: {message}")

        except Exception as e:
            logger.error(f"Error publishing WebSocket log: {e}")

    def log_error(self, worker_logger: logging.Logger, message: str, **kwargs) -> None:
        """Log an error message both to worker logs and WebSocket.

        Args:
            worker_logger: Worker logger instance for console/file logging
            message: Error message to log
            **kwargs: Additional logging kwargs
        """
        # Send to WebSocket for UI display
        self.publish_log(message, level=LogLevel.ERROR)

        # Log to worker logger for debugging
        worker_logger.error(message, **kwargs)

    def log_info(self, worker_logger: logging.Logger, message: str, **kwargs) -> None:
        """Log an info message both to worker logs and WebSocket.

        Args:
            worker_logger: Worker logger instance for console/file logging
            message: Info message to log
            **kwargs: Additional logging kwargs
        """
        # Send to WebSocket for UI display
        self.publish_log(message, level=LogLevel.INFO)

        # Log to worker logger for debugging
        worker_logger.info(message, **kwargs)

    def publish_update_log(
        self,
        state: LogState,
        message: str,
        component: str | LogComponent | None = None,
    ) -> None:
        """Publish update logs for monitoring workflow execution progress.

        These are used for status updates, progress indicators, and component state changes.

        Args:
            state: Log state (RUNNING, SUCCESS, ERROR, etc.)
            message: Update message
            component: Optional component name (SOURCE, DESTINATION, etc.)
        """
        try:
            if not self.messaging_channel:
                logger.warning(
                    f"No messaging channel, skipping WebSocket update: {message}"
                )
                return

            if isinstance(component, LogComponent):
                component = component.value

            log_details = LogPublisher.log_workflow_update(
                state=state.value,
                message=message,
                component=component,
            )

            # Publish to WebSocket channel
            success = LogPublisher.publish(self.messaging_channel, log_details)
            if not success:
                logger.warning(f"Failed to publish WebSocket update: {message}")

        except Exception as e:
            logger.error(f"Error publishing WebSocket update: {e}")

    def publish_initial_workflow_logs(self, total_files: int) -> None:
        """Publish initial workflow startup logs.

        Args:
            total_files: Total number of files to process
        """
        self.publish_update_log(
            LogState.BEGIN_WORKFLOW,
            f"Starting workflow execution with {total_files} files",
            LogComponent.WORKFLOW,
        )

    def publish_source_logs(self, files_found: int, files_filtered: int = 0) -> None:
        """Publish source connector logs.

        Args:
            files_found: Number of files found by source connector
            files_filtered: Number of files filtered out (optional)
        """
        if files_filtered > 0:
            message = f"Found {files_found} files, filtered to {files_found - files_filtered} files"
        else:
            message = f"Found {files_found} files from source"

        self.publish_update_log(LogState.SUCCESS, message, LogComponent.SOURCE)

    def publish_processing_start(
        self, file_name: str, current_idx: int, total_files: int
    ) -> None:
        """Publish file processing start log.

        Args:
            file_name: Name of file being processed
            current_idx: Current file index (1-based)
            total_files: Total number of files
        """
        message = f"Processing file {current_idx}/{total_files}: {file_name}"
        self.publish_log(message, LogLevel.INFO)

    def publish_processing_complete(
        self, file_name: str, success: bool, error: str | None = None
    ) -> None:
        """Publish file processing completion log.

        Args:
            file_name: Name of processed file
            success: Whether processing was successful
            error: Error message if processing failed
        """
        if success:
            message = f"✓ Successfully processed: {file_name}"
            level = LogLevel.INFO
        else:
            message = f"✗ Failed to process: {file_name}"
            if error:
                message += f" - {error}"
            level = LogLevel.ERROR

        self.publish_log(message, level)

    def publish_destination_logs(
        self, files_sent: int, destination_type: str = "destination"
    ) -> None:
        """Publish destination connector logs.

        Args:
            files_sent: Number of files sent to destination
            destination_type: Type of destination (destination, manual_review, etc.)
        """
        message = f"Sent {files_sent} files to {destination_type}"
        self.publish_update_log(LogState.SUCCESS, message, LogComponent.DESTINATION)

    def publish_execution_complete(
        self, successful_files: int, failed_files: int, total_time: float
    ) -> None:
        """Publish execution completion summary.

        Args:
            successful_files: Number of successfully processed files
            failed_files: Number of failed files
            total_time: Total execution time in seconds
        """
        if failed_files > 0:
            message = f"Execution completed: {successful_files} successful, {failed_files} failed ({total_time:.1f}s)"
            state = LogState.ERROR if successful_files == 0 else LogState.SUCCESS
        else:
            message = f"Execution completed successfully: {successful_files} files processed ({total_time:.1f}s)"
            state = LogState.SUCCESS

        self.publish_update_log(state, message, LogComponent.WORKFLOW)

    @classmethod
    def create_for_file_processing(
        cls,
        execution_id: str,
        file_execution_id: str | None = None,
        organization_id: str | None = None,
        pipeline_id: str | None = None,
    ) -> "WorkerWorkflowLogger":
        """Factory method for file processing workflows.

        Args:
            execution_id: Workflow execution ID
            file_execution_id: File execution ID
            organization_id: Organization ID
            pipeline_id: Pipeline ID

        Returns:
            Configured WorkerWorkflowLogger for file processing
        """
        return cls(
            execution_id=execution_id,
            log_stage=LogStage.PROCESSING,
            file_execution_id=file_execution_id,
            organization_id=organization_id,
            pipeline_id=pipeline_id,
        )

    @classmethod
    def create_for_source(
        cls,
        execution_id: str,
        organization_id: str | None = None,
        pipeline_id: str | None = None,
    ) -> "WorkerWorkflowLogger":
        """Factory method for source connector workflows.

        Args:
            execution_id: Workflow execution ID
            organization_id: Organization ID
            pipeline_id: Pipeline ID

        Returns:
            Configured WorkerWorkflowLogger for source processing
        """
        return cls(
            execution_id=execution_id,
            log_stage=LogStage.SOURCE,
            organization_id=organization_id,
            pipeline_id=pipeline_id,
        )

    @classmethod
    def create_for_general_workflow(
        cls,
        execution_id: str,
        organization_id: str | None = None,
        pipeline_id: str | None = None,
        log_events_id: str | None = None,
    ) -> "WorkerWorkflowLogger":
        """Factory method for general workflow execution.

        Args:
            execution_id: Workflow execution ID
            organization_id: Organization ID
            pipeline_id: Pipeline ID
            log_events_id: Log events ID

        Returns:
            Configured WorkerWorkflowLogger for general workflow
        """
        return cls(
            execution_id=execution_id,
            log_stage=LogStage.RUN,
            organization_id=organization_id,
            pipeline_id=pipeline_id,
            log_events_id=log_events_id,
        )

    def create_file_logger(self, file_execution_id: str) -> "WorkerWorkflowLogger":
        """Create a file-specific logger from an existing workflow logger.

        This preserves all the same settings but adds the file_execution_id for
        file-specific log tracking.

        Args:
            file_execution_id: WorkflowFileExecution ID to associate with logs

        Returns:
            New WorkerWorkflowLogger instance with file_execution_id
        """
        return WorkerWorkflowLogger(
            execution_id=self.execution_id,
            log_stage=self.log_stage,
            file_execution_id=file_execution_id,  # Add file association
            organization_id=self.organization_id,
            pipeline_id=None,  # Use the messaging channel from parent
            log_events_id=self.messaging_channel,  # Preserve messaging channel
        )
