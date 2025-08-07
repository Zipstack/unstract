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
    FileHash,
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

# Export constants and configuration
from .worker_constants import (
    APIEndpoints,
    CacheConfig,
    DefaultConfig,
    EnvVars,
    ErrorMessages,
    FileProcessingConfig,
    LogMessages,
    MonitoringConfig,
    QueueConfig,
    SecurityConfig,
    get_cache_key,
    get_task_max_retries,
    get_task_timeout,
    sanitize_filename,
    validate_execution_id,
    validate_organization_id,
)

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
    "FileHash",
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
    # Constants and configuration
    "APIEndpoints",
    "DefaultConfig",
    "ErrorMessages",
    "LogMessages",
    "QueueConfig",
    "FileProcessingConfig",
    "MonitoringConfig",
    "CacheConfig",
    "SecurityConfig",
    "EnvVars",
    "get_cache_key",
    "validate_execution_id",
    "validate_organization_id",
    "sanitize_filename",
    "get_task_timeout",
    "get_task_max_retries",
    # Existing utilities
    "LogFieldName",
    "LogEventArgument",
    "LogProcessingTask",
]
