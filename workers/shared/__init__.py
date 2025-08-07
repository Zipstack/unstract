"""Shared Worker Infrastructure

This module provides common infrastructure and utilities for lightweight Celery workers
that communicate with Django backend via internal APIs instead of direct ORM access.

Key components:
- API client with authentication
- Retry logic and circuit breakers
- Logging and monitoring utilities
- Configuration management
- Health check endpoints
- Worker-specific patterns (enums, dataclasses, base classes)
"""

# Existing infrastructure imports
from .api_client import InternalAPIClient
from .config import WorkerConfig
from .health import HealthChecker, HealthServer
from .logging_utils import WorkerLogger
from .retry_utils import CircuitBreaker, RetryHandler

# Import all worker patterns (when they're ready)
# from .enums import (
#     TaskName,
#     QueueName,
#     WorkerTaskStatus,
#     PipelineStatus,
#     WebhookStatus,
#     NotificationMethod,
# )

# from .models import (
#     TaskExecutionContext,
#     TaskError,
#     TaskPerformanceMetrics,
#     WorkerHealthMetrics,
#     WebhookResult,
#     FileExecutionResult,
#     BatchExecutionResult,
#     CallbackExecutionData,
#     WorkflowExecutionUpdateRequest,
#     PipelineStatusUpdateRequest,
#     NotificationRequest,
#     FileExecutionStatusUpdateRequest,
# )

# from .constants import (
#     APIEndpoints,
#     DefaultConfig,
#     QueueConfig,
#     FileProcessingConfig,
#     ErrorMessages,
#     LogMessages,
#     CacheConfig,
#     SecurityConfig,
#     MonitoringConfig,
#     EnvVars,
# )

# from .utils import (
#     StatusMappings,
#     validate_execution_id,
#     validate_organization_id,
#     sanitize_filename,
#     get_cache_key,
#     get_task_timeout,
#     get_task_max_retries,
# )

__all__ = [
    # Existing infrastructure
    "InternalAPIClient",
    "WorkerConfig",
    "WorkerLogger",
    "RetryHandler",
    "CircuitBreaker",
    "HealthChecker",
    "HealthServer",
    # Worker patterns (when ready)
    # Enums
    # "TaskName",
    # "QueueName",
    # "WorkerTaskStatus",
    # "PipelineStatus",
    # "WebhookStatus",
    # "NotificationMethod",
    # Models
    # "TaskExecutionContext",
    # "TaskError",
    # "TaskPerformanceMetrics",
    # "WorkerHealthMetrics",
    # "WebhookResult",
    # "FileExecutionResult",
    # "BatchExecutionResult",
    # "CallbackExecutionData",
    # "WorkflowExecutionUpdateRequest",
    # "PipelineStatusUpdateRequest",
    # "NotificationRequest",
    # "FileExecutionStatusUpdateRequest",
    # Constants
    # "APIEndpoints",
    # "DefaultConfig",
    # "QueueConfig",
    # "FileProcessingConfig",
    # "ErrorMessages",
    # "LogMessages",
    # "CacheConfig",
    # "SecurityConfig",
    # "MonitoringConfig",
    # "EnvVars",
    # Utils
    # "StatusMappings",
    # "validate_execution_id",
    # "validate_organization_id",
    # "sanitize_filename",
    # "get_cache_key",
    # "get_task_timeout",
    # "get_task_max_retries",
]

__version__ = "1.0.0"
