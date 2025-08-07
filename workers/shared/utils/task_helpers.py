"""Task Helper Utilities

Helper functions for task configuration and management.
"""

from ..constants import DefaultConfig


def get_task_timeout(task_name: str) -> int:
    """Get timeout for specific task type."""
    timeouts = {
        "process_file_batch": DefaultConfig.FILE_PROCESSING_TIMEOUT,
        "process_batch_callback": DefaultConfig.CALLBACK_TIMEOUT,
        "send_webhook_notification": DefaultConfig.WEBHOOK_TIMEOUT,
    }
    return timeouts.get(task_name, DefaultConfig.DEFAULT_TASK_TIMEOUT)


def get_task_max_retries(task_name: str) -> int:
    """Get max retries for specific task type."""
    retries = {
        "process_file_batch": DefaultConfig.FILE_PROCESSING_MAX_RETRIES,
        "process_batch_callback": DefaultConfig.CALLBACK_MAX_RETRIES,
        "send_webhook_notification": DefaultConfig.WEBHOOK_MAX_RETRIES,
    }
    return retries.get(task_name, DefaultConfig.DEFAULT_MAX_RETRIES)
