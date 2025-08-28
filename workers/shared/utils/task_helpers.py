"""Task Helper Utilities

Helper functions for task configuration and management.
"""

# Avoid circular import - define constants directly
# from ..infrastructure.config import DefaultConfig

# Default timeouts to avoid circular imports
DEFAULT_FILE_PROCESSING_TIMEOUT = 1800  # 30 minutes
DEFAULT_CALLBACK_TIMEOUT = 600  # 10 minutes
DEFAULT_WEBHOOK_TIMEOUT = 30  # 30 seconds

# Default retry counts to avoid circular imports
DEFAULT_FILE_PROCESSING_MAX_RETRIES = 3
DEFAULT_CALLBACK_MAX_RETRIES = 2
DEFAULT_WEBHOOK_MAX_RETRIES = 3


def get_task_timeout(task_name: str) -> int:
    """Get timeout for specific task type."""
    timeouts = {
        "process_file_batch": DEFAULT_FILE_PROCESSING_TIMEOUT,
        "process_batch_callback": DEFAULT_CALLBACK_TIMEOUT,
        "send_webhook_notification": DEFAULT_WEBHOOK_TIMEOUT,
    }
    return timeouts.get(task_name, 300)  # 5 minutes default


def get_task_max_retries(task_name: str) -> int:
    """Get max retries for specific task type."""
    retries = {
        "process_file_batch": DEFAULT_FILE_PROCESSING_MAX_RETRIES,
        "process_batch_callback": DEFAULT_CALLBACK_MAX_RETRIES,
        "send_webhook_notification": DEFAULT_WEBHOOK_MAX_RETRIES,
    }
    return retries.get(task_name, 3)  # Default 3 retries
