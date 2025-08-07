"""Worker-Specific Data Models and Enums

This module provides worker-specific data models, enums, and base classes
to replace hardcoded strings and dict patterns in the workers codebase.
These models extend the core data models with worker-specific functionality.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .data_models import ExecutionStatus, serialize_dataclass_to_dict

logger = logging.getLogger(__name__)


# Task and Queue Enums
class TaskName(str, Enum):
    """Standardized task names across all workers."""

    # General worker tasks
    SEND_WEBHOOK_NOTIFICATION = "send_webhook_notification"
    ASYNC_EXECUTE_BIN_API = "async_execute_bin_api"
    EXECUTE_WORKFLOW_WITH_FILES = "execute_workflow_with_files"
    ORCHESTRATE_FILE_PROCESSING = "_orchestrate_file_processing_general"

    # File processing worker tasks
    PROCESS_FILE_BATCH = "process_file_batch"
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


class WorkerTaskStatus(str, Enum):
    """Task execution status for workers."""

    PENDING = "PENDING"
    STARTED = "STARTED"
    RETRY = "RETRY"
    FAILURE = "FAILURE"
    SUCCESS = "SUCCESS"
    REVOKED = "REVOKED"

    def __str__(self):
        """Return enum value for Celery status comparison."""
        return self.value


class PipelineStatus(str, Enum):
    """Pipeline execution status mapping."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    INPROGRESS = "INPROGRESS"
    YET_TO_START = "YET_TO_START"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"

    def __str__(self):
        """Return enum value for API updates."""
        return self.value


class WebhookStatus(str, Enum):
    """Webhook delivery status."""

    DELIVERED = "delivered"
    QUEUED = "queued"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRY = "retry"

    def __str__(self):
        """Return enum value for webhook tracking."""
        return self.value


class NotificationMethod(str, Enum):
    """Notification delivery methods."""

    WEBHOOK = "webhook"
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"

    def __str__(self):
        """Return enum value for notification routing."""
        return self.value


# Status Mapping Utilities
class StatusMappings:
    """Utilities for mapping between different status systems."""

    EXECUTION_TO_PIPELINE = {
        ExecutionStatus.COMPLETED: PipelineStatus.SUCCESS,
        ExecutionStatus.ERROR: PipelineStatus.FAILURE,
        ExecutionStatus.STOPPED: PipelineStatus.FAILURE,
        ExecutionStatus.EXECUTING: PipelineStatus.INPROGRESS,
        ExecutionStatus.PENDING: PipelineStatus.YET_TO_START,
        ExecutionStatus.QUEUED: PipelineStatus.YET_TO_START,  # Legacy compatibility
        ExecutionStatus.CANCELED: PipelineStatus.FAILURE,  # Legacy compatibility
    }

    PIPELINE_TO_EXECUTION = {
        PipelineStatus.SUCCESS: ExecutionStatus.COMPLETED,
        PipelineStatus.FAILURE: ExecutionStatus.ERROR,
        PipelineStatus.INPROGRESS: ExecutionStatus.EXECUTING,
        PipelineStatus.YET_TO_START: ExecutionStatus.PENDING,
        PipelineStatus.PARTIAL_SUCCESS: ExecutionStatus.COMPLETED,
    }

    @classmethod
    def execution_to_pipeline(cls, execution_status: ExecutionStatus) -> PipelineStatus:
        """Map execution status to pipeline status."""
        return cls.EXECUTION_TO_PIPELINE.get(execution_status, PipelineStatus.FAILURE)

    @classmethod
    def pipeline_to_execution(cls, pipeline_status: PipelineStatus) -> ExecutionStatus:
        """Map pipeline status to execution status."""
        return cls.PIPELINE_TO_EXECUTION.get(pipeline_status, ExecutionStatus.ERROR)

    @classmethod
    def is_final_status(cls, status: ExecutionStatus) -> bool:
        """Check if execution status is final (no further processing)."""
        return status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.ERROR,
            ExecutionStatus.STOPPED,
        ]


# Task Result Data Models
@dataclass
class WebhookResult:
    """Structured result for webhook delivery tasks."""

    status: WebhookStatus
    url: str
    task_id: str
    webhook_task_id: str
    webhook_status: str
    payload_size: int
    timeout: int
    attempts: int
    delivery_time: float
    error_message: str | None = None
    response_code: int | None = None
    response_body: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebhookResult":
        """Create from dictionary (e.g., task result)."""
        return cls(
            status=WebhookStatus(data.get("status", WebhookStatus.FAILED)),
            url=data.get("url", ""),
            task_id=data.get("task_id", ""),
            webhook_task_id=data.get("webhook_task_id", ""),
            webhook_status=data.get("webhook_status", ""),
            payload_size=data.get("payload_size", 0),
            timeout=data.get("timeout", 30),
            attempts=data.get("attempts", 1),
            delivery_time=data.get("delivery_time", 0.0),
            error_message=data.get("error_message"),
            response_code=data.get("response_code"),
            response_body=data.get("response_body"),
        )


@dataclass
class FileExecutionResult:
    """Structured result for file execution tasks."""

    file: str
    file_execution_id: str | None
    status: ExecutionStatus
    error: str | None = None
    result: Any | None = None
    metadata: dict[str, Any] | None = None
    processing_time: float = 0.0
    file_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileExecutionResult":
        """Create from dictionary (e.g., task result)."""
        status_str = data.get("status", ExecutionStatus.ERROR.value)
        status = (
            ExecutionStatus(status_str) if isinstance(status_str, str) else status_str
        )

        return cls(
            file=data.get("file", ""),
            file_execution_id=data.get("file_execution_id"),
            status=status,
            error=data.get("error"),
            result=data.get("result"),
            metadata=data.get("metadata"),
            processing_time=data.get("processing_time", 0.0),
            file_size=data.get("file_size", 0),
        )

    def is_successful(self) -> bool:
        """Check if file execution was successful."""
        return self.status in [ExecutionStatus.COMPLETED, ExecutionStatus.SUCCESS]

    def has_error(self) -> bool:
        """Check if file execution had errors."""
        return self.error is not None or self.status == ExecutionStatus.ERROR


@dataclass
class BatchExecutionResult:
    """Structured result for batch execution tasks."""

    total_files: int
    successful_files: int
    failed_files: int
    execution_time: float
    file_results: list[FileExecutionResult] = field(default_factory=list)
    batch_id: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.successful_files / self.total_files) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BatchExecutionResult":
        """Create from dictionary (e.g., task result)."""
        file_results = [
            FileExecutionResult.from_dict(result)
            for result in data.get("file_results", [])
        ]

        return cls(
            total_files=data.get("total_files", 0),
            successful_files=data.get("successful_files", 0),
            failed_files=data.get("failed_files", 0),
            execution_time=data.get("execution_time", 0.0),
            file_results=file_results,
            batch_id=data.get("batch_id"),
            errors=data.get("errors", []),
        )

    def add_file_result(self, file_result: FileExecutionResult):
        """Add a file execution result to the batch."""
        self.file_results.append(file_result)
        self.total_files = len(self.file_results)

        if file_result.is_successful():
            self.successful_files += 1
        else:
            self.failed_files += 1

        self.execution_time += file_result.processing_time


@dataclass
class CallbackExecutionData:
    """Data structure for callback task execution context."""

    execution_id: str
    pipeline_id: str
    organization_id: str
    workflow_id: str
    batch_results: list[BatchExecutionResult] = field(default_factory=list)
    total_batches: int = 0
    completed_batches: int = 0
    callback_triggered_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API serialization."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CallbackExecutionData":
        """Create from dictionary (e.g., callback kwargs)."""
        batch_results = [
            BatchExecutionResult.from_dict(result)
            for result in data.get("batch_results", [])
        ]

        return cls(
            execution_id=data.get("execution_id", ""),
            pipeline_id=data.get("pipeline_id", ""),
            organization_id=data.get("organization_id", ""),
            workflow_id=data.get("workflow_id", ""),
            batch_results=batch_results,
            total_batches=data.get("total_batches", 0),
            completed_batches=data.get("completed_batches", 0),
            callback_triggered_at=data.get("callback_triggered_at"),
        )

    @property
    def total_files_processed(self) -> int:
        """Calculate total files processed across all batches."""
        return sum(batch.total_files for batch in self.batch_results)

    @property
    def total_successful_files(self) -> int:
        """Calculate total successful files across all batches."""
        return sum(batch.successful_files for batch in self.batch_results)

    @property
    def total_failed_files(self) -> int:
        """Calculate total failed files across all batches."""
        return sum(batch.failed_files for batch in self.batch_results)

    @property
    def overall_success_rate(self) -> float:
        """Calculate overall success rate across all batches."""
        total = self.total_files_processed
        if total == 0:
            return 0.0
        return (self.total_successful_files / total) * 100

    def determine_final_status(self) -> ExecutionStatus:
        """Determine final execution status based on batch results."""
        if not self.batch_results:
            return ExecutionStatus.ERROR

        total_files = self.total_files_processed
        successful_files = self.total_successful_files

        if total_files == 0:
            return ExecutionStatus.ERROR
        elif successful_files == total_files:
            return ExecutionStatus.COMPLETED
        elif successful_files > 0:
            return ExecutionStatus.COMPLETED  # Partial success still marked as completed
        else:
            return ExecutionStatus.ERROR


# API Request/Response Data Models
@dataclass
class WorkflowExecutionUpdateRequest:
    """Request data for updating workflow execution status."""

    status: ExecutionStatus
    error_message: str | None = None
    result: dict[str, Any] | None = None
    execution_time: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        data = {"status": self.status.value}
        if self.error_message:
            data["error_message"] = self.error_message
        if self.result:
            data["result"] = self.result
        if self.execution_time:
            data["execution_time"] = self.execution_time
        return data


@dataclass
class PipelineStatusUpdateRequest:
    """Request data for updating pipeline status."""

    status: PipelineStatus
    last_run_details: dict[str, Any] | None = None
    execution_summary: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        data = {"status": self.status.value}
        if self.last_run_details:
            data["last_run_details"] = self.last_run_details
        if self.execution_summary:
            data["execution_summary"] = self.execution_summary
        return data


@dataclass
class NotificationRequest:
    """Request data for sending notifications."""

    method: NotificationMethod
    recipients: list[str]
    subject: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
    priority: str = "normal"  # low, normal, high, urgent

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        return serialize_dataclass_to_dict(self)


# Performance Monitoring Data Models
@dataclass
class TaskPerformanceMetrics:
    """Performance metrics for task execution monitoring."""

    task_name: str
    execution_time: float
    memory_usage: float | None = None
    cpu_usage: float | None = None
    error_count: int = 0
    retry_count: int = 0
    timestamp: datetime | None = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for metrics collection."""
        return serialize_dataclass_to_dict(self)


@dataclass
class WorkerHealthMetrics:
    """Health metrics for worker instances."""

    worker_name: str
    worker_version: str
    uptime: float
    active_tasks: int
    completed_tasks: int
    failed_tasks: int
    memory_usage: float | None = None
    cpu_usage: float | None = None
    last_heartbeat: datetime | None = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.last_heartbeat is None:
            self.last_heartbeat = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for health monitoring."""
        return serialize_dataclass_to_dict(self)

    @property
    def success_rate(self) -> float:
        """Calculate task success rate."""
        total_tasks = self.completed_tasks + self.failed_tasks
        if total_tasks == 0:
            return 100.0
        return (self.completed_tasks / total_tasks) * 100


# Task Context Data Models
@dataclass
class TaskExecutionContext:
    """Execution context for worker tasks."""

    task_id: str
    task_name: TaskName
    organization_id: str
    execution_id: str | None = None
    workflow_id: str | None = None
    pipeline_id: str | None = None
    user_id: str | None = None
    correlation_id: str | None = None
    retry_count: int = 0
    started_at: datetime | None = None

    def __post_init__(self):
        """Set started_at if not provided."""
        if self.started_at is None:
            self.started_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging and tracing."""
        return serialize_dataclass_to_dict(self)

    def get_log_context(self) -> dict[str, Any]:
        """Get context suitable for structured logging."""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name.value,
            "organization_id": self.organization_id,
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "pipeline_id": self.pipeline_id,
            "retry_count": self.retry_count,
        }


# Configuration Data Models
@dataclass
class TaskRetryConfig:
    """Configuration for task retry behavior."""

    max_retries: int = 3
    retry_backoff: bool = True
    retry_backoff_max: int = 500
    retry_jitter: bool = True
    autoretry_for: tuple[type, ...] = field(default_factory=lambda: (Exception,))

    def to_celery_kwargs(self) -> dict[str, Any]:
        """Convert to Celery task decorator kwargs."""
        return {
            "max_retries": self.max_retries,
            "retry_backoff": self.retry_backoff,
            "retry_backoff_max": self.retry_backoff_max,
            "retry_jitter": self.retry_jitter,
            "autoretry_for": self.autoretry_for,
        }


@dataclass
class TaskTimeoutConfig:
    """Configuration for task timeout behavior."""

    soft_time_limit: int = 300  # 5 minutes
    time_limit: int = 330  # 5.5 minutes (30s buffer)
    task_acks_late: bool = True
    task_reject_on_worker_lost: bool = True

    def to_celery_kwargs(self) -> dict[str, Any]:
        """Convert to Celery task decorator kwargs."""
        return {
            "soft_time_limit": self.soft_time_limit,
            "time_limit": self.time_limit,
            "task_acks_late": self.task_acks_late,
            "task_reject_on_worker_lost": self.task_reject_on_worker_lost,
        }


# Error Handling Data Models
@dataclass
class TaskError:
    """Structured error information for task failures."""

    task_id: str
    task_name: TaskName
    error_type: str
    error_message: str
    traceback: str | None = None
    retry_count: int = 0
    occurred_at: datetime | None = None

    def __post_init__(self):
        """Set occurred_at if not provided."""
        if self.occurred_at is None:
            self.occurred_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for error reporting."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_exception(
        cls, task_id: str, task_name: TaskName, exception: Exception, retry_count: int = 0
    ) -> "TaskError":
        """Create from Python exception."""
        import traceback as tb

        return cls(
            task_id=task_id,
            task_name=task_name,
            error_type=type(exception).__name__,
            error_message=str(exception),
            traceback=tb.format_exc(),
            retry_count=retry_count,
        )
