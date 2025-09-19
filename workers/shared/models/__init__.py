"""Worker Data Models

Dataclasses and models specific to worker implementation.
"""

from unstract.core.worker_models import FileExecutionResult

from .batch_models import (
    FileStatusUpdateRequest,
    PipelineUpdateRequest,
    StatusUpdateRequest,
    WebhookNotificationRequest,
)
from .callback_models import CallbackExecutionData
from .file_processing import FileProcessingContext
from .request_models import (
    FileExecutionStatusUpdateRequest,
    NotificationRequest,
    PipelineStatusUpdateRequest,
    WorkflowExecutionUpdateRequest,
)
from .result_models import BatchExecutionResult, WebhookResult
from .task_models import (
    TaskError,
    TaskExecutionContext,
    TaskPerformanceMetrics,
    WorkerHealthMetrics,
)

__all__ = [
    # Task models
    "TaskExecutionContext",
    "TaskError",
    "TaskPerformanceMetrics",
    "WorkerHealthMetrics",
    # Result models
    "WebhookResult",
    "FileExecutionResult",
    "BatchExecutionResult",
    # Callback models
    "CallbackExecutionData",
    # Request models
    "WorkflowExecutionUpdateRequest",
    "PipelineStatusUpdateRequest",
    "NotificationRequest",
    "FileExecutionStatusUpdateRequest",
    # Batch models
    "StatusUpdateRequest",
    "PipelineUpdateRequest",
    "FileStatusUpdateRequest",
    "WebhookNotificationRequest",
    # File processing models
    "FileProcessingContext",
]
