"""Task and Queue Enumerations

Worker-specific task names and queue names.
"""

from enum import Enum


class TaskName(str, Enum):
    """Standardized task names across all workers."""

    # General worker tasks
    SEND_WEBHOOK_NOTIFICATION = "send_webhook_notification"
    ASYNC_EXECUTE_BIN_GENERAL = "async_execute_bin_general"
    EXECUTE_WORKFLOW_WITH_FILES = "execute_workflow_with_files"
    ORCHESTRATE_FILE_PROCESSING = "_orchestrate_file_processing_general"

    # API deployment worker tasks
    ASYNC_EXECUTE_BIN_API = "async_execute_bin_api"
    ASYNC_EXECUTE_BIN = "async_execute_bin"

    # File processing worker tasks
    PROCESS_FILE_BATCH = "process_file_batch"
    PROCESS_FILE_BATCH_API = "process_file_batch_api"
    EXECUTE_SINGLE_FILE = "execute_single_file"
    UPDATE_FILE_EXECUTION_STATUS = "update_file_execution_status"

    # Callback worker tasks
    PROCESS_BATCH_CALLBACK = "process_batch_callback"
    UPDATE_WORKFLOW_EXECUTION_STATUS = "update_workflow_execution_status"
    UPDATE_PIPELINE_STATUS = "update_pipeline_status"

    # API deployment worker tasks
    CHECK_API_DEPLOYMENT_STATUS = "check_api_deployment_status"

    # Structure tool task (runs in file_processing worker)
    EXECUTE_STRUCTURE_TOOL = "execute_structure_tool"

    # Executor worker tasks
    EXECUTE_EXTRACTION = "execute_extraction"

    def __str__(self):
        """Return enum value for Celery task naming."""
        return self.value
