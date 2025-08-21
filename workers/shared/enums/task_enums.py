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
    DEPLOY_API_WORKFLOW = "deploy_api_workflow"
    UNDEPLOY_API_WORKFLOW = "undeploy_api_workflow"
    CHECK_API_DEPLOYMENT_STATUS = "check_api_deployment_status"

    def __str__(self):
        """Return enum value for Celery task naming."""
        return self.value


class QueueName(str, Enum):
    """Standardized queue names across all workers."""

    # Standard Celery queues
    CELERY = "celery"
    CELERY_API_DEPLOYMENTS = "celery_api_deployments"
    CELERY_LOG_TASK_QUEUE = "celery_log_task_queue"
    CELERY_PERIODIC_LOGS = "celery_periodic_logs"

    # Worker-specific queues
    GENERAL = "general"
    FILE_PROCESSING = "file_processing"
    CALLBACK = "callback"
    API_DEPLOYMENTS = "api_deployments"
    WEBHOOK = "webhook"

    # Callback-specific queues
    FILE_PROCESSING_CALLBACK = "file_processing_callback"
    GENERAL_CALLBACK = "general_callback"

    def __str__(self):
        """Return enum value for Celery queue routing."""
        return self.value
