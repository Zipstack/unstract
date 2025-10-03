"""Unstract Core Library

Core data models, utilities, and base classes for the Unstract platform.
Provides shared functionality between backend and worker services.
"""

# Export core data models and enums
# Export existing utilities and constants
from .constants import LogEventArgument, LogFieldName, LogProcessingTask
from .data_models import (
    ConnectionType,
    ExecutionStatus,
    FileHashData,
    SourceConnectionType,
    WorkflowExecutionData,
    WorkflowFileExecutionData,
    WorkflowType,
    serialize_dataclass_to_dict,
)

# Export worker base classes
from .worker_base import (
    CallbackTaskBase,
    FileProcessingTaskBase,
    WorkerTaskBase,
    circuit_breaker,
    create_callback_task,
    create_file_processing_task,
    create_task_decorator,
    monitor_performance,
    with_task_context,
)

# Note: Worker constants moved to workers/shared/ to remove Django dependency
# These are now available directly from workers.shared.constants and workers.shared.worker_patterns
# Export worker-specific models and enums
from .worker_models import (
    BatchExecutionResult,
    CallbackExecutionData,
    FileExecutionResult,
    NotificationMethod,
    NotificationRequest,
    PipelineStatus,
    PipelineStatusUpdateRequest,
    QueueName,
    StatusMappings,
    TaskError,
    TaskExecutionContext,
    TaskName,
    WebhookResult,
    WebhookStatus,
    WorkerTaskStatus,
    WorkflowExecutionUpdateRequest,
)

__version__ = "1.0.0"

__all__ = [
    # Core data models and enums
    "ExecutionStatus",
    "WorkflowType",
    "ConnectionType",
    "FileHashData",
    "WorkflowFileExecutionData",
    "WorkflowExecutionData",
    "SourceConnectionType",
    "serialize_dataclass_to_dict",
    # Worker models and enums
    "TaskName",
    "QueueName",
    "WorkerTaskStatus",
    "PipelineStatus",
    "WebhookStatus",
    "NotificationMethod",
    "StatusMappings",
    "WebhookResult",
    "FileExecutionResult",
    "BatchExecutionResult",
    "CallbackExecutionData",
    "WorkflowExecutionUpdateRequest",
    "PipelineStatusUpdateRequest",
    "NotificationRequest",
    "TaskExecutionContext",
    "TaskError",
    # Worker base classes
    "WorkerTaskBase",
    "FileProcessingTaskBase",
    "CallbackTaskBase",
    "create_task_decorator",
    "monitor_performance",
    "with_task_context",
    "circuit_breaker",
    "create_file_processing_task",
    "create_callback_task",
    # Existing utilities
    "LogFieldName",
    "LogEventArgument",
    "LogProcessingTask",
]
