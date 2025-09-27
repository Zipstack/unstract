"""Logging Helper Functions

Utility functions to reduce repetitive null checking and make logging code cleaner and more readable.
"""

from unstract.workflow_execution.enums import LogLevel, LogStage

from .workflow_logger import WorkerWorkflowLogger


def safe_publish_processing_start(
    workflow_logger: WorkerWorkflowLogger | None,
    file_execution_id: str | None,
    file_name: str,
    current_file_idx: int,
    total_files: int,
    execution_id: str | None = None,
    organization_id: str | None = None,
) -> None:
    """Safely publish processing start log with proper null checking.

    Args:
        workflow_logger: WorkerWorkflowLogger instance (can be None)
        file_execution_id: File execution ID for file-specific logging (can be None)
        file_name: Name of the file being processed
        current_file_idx: Current file index
        total_files: Total number of files
        execution_id: Execution ID for fallback logger creation
        organization_id: Organization ID for fallback logger creation
    """
    if not workflow_logger:
        return

    if file_execution_id:
        # Create file-specific logger to associate logs with WorkflowFileExecution
        file_logger = workflow_logger.create_file_logger(file_execution_id)
        file_logger.publish_processing_start(file_name, current_file_idx, total_files)
    else:
        # Fallback to execution-level logging if no file_execution_id
        workflow_logger.publish_processing_start(file_name, current_file_idx, total_files)


def safe_publish_processing_complete(
    workflow_logger: WorkerWorkflowLogger | None,
    file_execution_id: str | None,
    file_name: str,
    success: bool,
    error: str | None = None,
    execution_id: str | None = None,
    organization_id: str | None = None,
) -> None:
    """Safely publish processing completion log with proper null checking.

    Args:
        workflow_logger: WorkerWorkflowLogger instance (can be None)
        file_execution_id: File execution ID for file-specific logging (can be None)
        file_name: Name of the processed file
        success: Whether processing was successful
        error: Error message if processing failed
        execution_id: Execution ID for fallback logger creation
        organization_id: Organization ID for fallback logger creation
    """
    if not workflow_logger:
        return

    if file_execution_id:
        # Create file-specific logger for this completion
        file_logger = workflow_logger.create_file_logger(file_execution_id)
        file_logger.publish_processing_complete(file_name, success, error)
    else:
        # Fallback to execution-level logging
        workflow_logger.publish_processing_complete(file_name, success, error)


def safe_publish_log(
    workflow_logger: WorkerWorkflowLogger | None,
    file_execution_id: str | None,
    message: str,
    level: LogLevel = LogLevel.INFO,
    execution_id: str | None = None,
    organization_id: str | None = None,
) -> None:
    """Safely publish a general log message with proper null checking.

    Args:
        workflow_logger: WorkerWorkflowLogger instance (can be None)
        file_execution_id: File execution ID for file-specific logging (can be None)
        message: Log message to publish
        level: Log level (INFO, ERROR, etc.)
        execution_id: Execution ID for fallback logger creation
        organization_id: Organization ID for fallback logger creation
    """
    if not workflow_logger:
        return

    if file_execution_id:
        # Create file-specific logger for this message
        file_logger = workflow_logger.create_file_logger(file_execution_id)
        file_logger.publish_log(message, level)
    else:
        # Fallback to execution-level logging
        workflow_logger.publish_log(message, level)


def create_file_logger_safe(
    workflow_logger: WorkerWorkflowLogger | None,
    file_execution_id: str | None,
    execution_id: str | None = None,
    organization_id: str | None = None,
    log_stage: LogStage = LogStage.PROCESSING,
) -> WorkerWorkflowLogger | None:
    """Safely create a file-specific logger with null checking.

    Args:
        workflow_logger: Parent workflow logger (can be None)
        file_execution_id: File execution ID (can be None)
        execution_id: Execution ID for fallback logger creation
        organization_id: Organization ID for fallback logger creation
        log_stage: Log stage for new logger creation

    Returns:
        File-specific logger or None if inputs are invalid
    """
    if not workflow_logger or not file_execution_id:
        return workflow_logger  # Return parent logger or None

    try:
        return workflow_logger.create_file_logger(file_execution_id)
    except Exception:
        # If file logger creation fails, return parent logger
        return workflow_logger


def ensure_workflow_logger(
    workflow_logger: WorkerWorkflowLogger | None,
    execution_id: str,
    organization_id: str | None = None,
    pipeline_id: str | None = None,
    log_stage: LogStage = LogStage.PROCESSING,
) -> WorkerWorkflowLogger | None:
    """Ensure a workflow logger exists, creating one if needed.

    Args:
        workflow_logger: Existing workflow logger (can be None)
        execution_id: Execution ID for logger creation
        organization_id: Organization ID for logger creation
        pipeline_id: Pipeline ID for logger creation
        log_stage: Log stage for logger creation

    Returns:
        WorkerWorkflowLogger instance or None if creation fails
    """
    if workflow_logger:
        return workflow_logger

    if not execution_id:
        return None

    try:
        return WorkerWorkflowLogger(
            execution_id=execution_id,
            log_stage=log_stage,
            organization_id=organization_id,
            pipeline_id=pipeline_id,
        )
    except Exception:
        return None


def with_file_logging(
    workflow_logger: WorkerWorkflowLogger | None,
    file_execution_id: str | None,
    execution_id: str | None = None,
    organization_id: str | None = None,
):
    """Context manager for file-specific logging operations.

    Usage:
        with with_file_logging(workflow_logger, file_execution_id) as logger:
            if logger:
                logger.publish_log("Processing file...")

    Args:
        workflow_logger: Parent workflow logger (can be None)
        file_execution_id: File execution ID (can be None)
        execution_id: Execution ID for fallback
        organization_id: Organization ID for fallback

    Returns:
        Context manager that yields appropriate logger or None
    """

    class LoggingContext:
        def __init__(self, logger):
            self.logger = logger

        def __enter__(self):
            return self.logger

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    # Return file-specific logger if available, otherwise parent logger
    if workflow_logger and file_execution_id:
        try:
            file_logger = workflow_logger.create_file_logger(file_execution_id)
            return LoggingContext(file_logger)
        except Exception:
            pass

    return LoggingContext(workflow_logger)


# Convenience functions for common logging patterns
def log_file_processing_start(
    workflow_logger: WorkerWorkflowLogger | None,
    file_execution_id: str | None,
    file_name: str,
    current_idx: int,
    total_files: int,
) -> None:
    """Log file processing start with automatic null checking."""
    safe_publish_processing_start(
        workflow_logger, file_execution_id, file_name, current_idx, total_files
    )


def log_file_processing_success(
    workflow_logger: WorkerWorkflowLogger | None,
    file_execution_id: str | None,
    file_name: str,
) -> None:
    """Log file processing success with automatic null checking."""
    safe_publish_processing_complete(
        workflow_logger, file_execution_id, file_name, success=True
    )


def log_file_processing_error(
    workflow_logger: WorkerWorkflowLogger | None,
    file_execution_id: str | None,
    file_name: str,
    error: str,
) -> None:
    """Log file processing error with automatic null checking."""
    safe_publish_processing_complete(
        workflow_logger, file_execution_id, file_name, success=False, error=error
    )


def log_file_info(
    workflow_logger: WorkerWorkflowLogger | None,
    file_execution_id: str | None,
    message: str,
) -> None:
    """Log file info message with automatic null checking."""
    safe_publish_log(workflow_logger, file_execution_id, message, LogLevel.INFO)


def log_file_error(
    workflow_logger: WorkerWorkflowLogger | None,
    file_execution_id: str | None,
    message: str,
) -> None:
    """Log file error message with automatic null checking."""
    safe_publish_log(workflow_logger, file_execution_id, message, LogLevel.ERROR)
