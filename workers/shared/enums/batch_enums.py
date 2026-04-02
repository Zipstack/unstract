"""Batch Operation Enumerations

Enums for batch processing operations.
"""

from enum import Enum


class BatchOperationType(str, Enum):
    """Types of batch operations."""

    STATUS_UPDATE = "status_update"
    PIPELINE_UPDATE = "pipeline_update"
    FILE_STATUS_UPDATE = "file_status_update"
    WEBHOOK_NOTIFICATION = "webhook_notification"

    def __str__(self):
        """Return string value for operation type."""
        return self.value
