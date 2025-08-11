"""Worker-Specific Patterns

This module contains worker-specific dataclasses, enums, and patterns
that are only used within the worker services. Domain models that are
shared between backend and workers remain in unstract.core.
"""

import logging
import os

# Import only the shared domain models from core
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../unstract/core/src"))

from unstract.core import ExecutionStatus, serialize_dataclass_to_dict

logger = logging.getLogger(__name__)


# Worker-Specific Enums (NOT in core)
class TaskName(str, Enum):
    """Worker task names - only used by workers."""

    SEND_WEBHOOK_NOTIFICATION = "send_webhook_notification"
    ASYNC_EXECUTE_BIN_API = "async_execute_bin_api"
    EXECUTE_WORKFLOW_WITH_FILES = "execute_workflow_with_files"
    ORCHESTRATE_FILE_PROCESSING = "_orchestrate_file_processing_general"
    PROCESS_FILE_BATCH = "process_file_batch"
    PROCESS_BATCH_CALLBACK = "process_batch_callback"

    def __str__(self):
        return self.value


class QueueName(str, Enum):
    """Worker queue names - only used by workers."""

    GENERAL = "general"
    FILE_PROCESSING = "file_processing"
    CALLBACK = "callback"
    API_DEPLOYMENTS = "api_deployments"

    def __str__(self):
        return self.value


class WebhookStatus(str, Enum):
    """Webhook delivery status - worker implementation detail."""

    DELIVERED = "delivered"
    QUEUED = "queued"
    FAILED = "failed"
    TIMEOUT = "timeout"

    def __str__(self):
        return self.value


class PipelineStatus(str, Enum):
    """Pipeline status for worker-backend communication."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    INPROGRESS = "INPROGRESS"
    YET_TO_START = "YET_TO_START"

    def __str__(self):
        return self.value


# Worker-Specific Data Models
@dataclass
class WebhookResult:
    """Worker webhook delivery result - not used by backend directly."""

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

    def to_dict(self) -> dict[str, Any]:
        return serialize_dataclass_to_dict(self)


@dataclass
class FileExecutionResult:
    """Worker file execution result - worker implementation detail."""

    file: str
    file_execution_id: str | None
    status: ExecutionStatus  # Uses shared enum from core
    error: str | None = None
    result: Any | None = None
    metadata: dict[str, Any] | None = None
    processing_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return serialize_dataclass_to_dict(self)

    def is_successful(self) -> bool:
        return self.status == ExecutionStatus.COMPLETED


@dataclass
class BatchExecutionResult:
    """Worker batch processing result - worker-specific aggregation."""

    total_files: int
    successful_files: int
    failed_files: int
    execution_time: float
    file_results: list[FileExecutionResult] = field(default_factory=list)
    batch_id: str | None = None

    @property
    def success_rate(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.successful_files / self.total_files) * 100

    def to_dict(self) -> dict[str, Any]:
        return serialize_dataclass_to_dict(self)


# Worker Configuration and Constants

# Internal API Configuration - Environment configurable
INTERNAL_API_PREFIX = os.getenv("INTERNAL_API_PREFIX", "/internal")
INTERNAL_API_VERSION = os.getenv("INTERNAL_API_VERSION", "v1")
INTERNAL_API_BASE_PATH = f"{INTERNAL_API_PREFIX}/{INTERNAL_API_VERSION}"


def build_internal_endpoint(path: str) -> str:
    """Build a complete internal API endpoint path.

    Args:
        path: The endpoint path without the internal prefix (e.g., "health/")

    Returns:
        Complete internal API path (e.g., "/internal/v1/health/")
    """
    # Ensure path starts and ends with /
    if not path.startswith("/"):
        path = f"/{path}"
    if not path.endswith("/"):
        path = f"{path}/"

    return f"{INTERNAL_API_BASE_PATH}{path}"


class APIEndpoints:
    """Internal API endpoints - worker implementation detail with environment configuration."""

    WORKFLOW_EXECUTION_STATUS = build_internal_endpoint(
        "workflow-execution/{execution_id}/status/"
    )
    WORKFLOW_FILE_EXECUTION_CREATE = build_internal_endpoint(
        "workflow-file-execution/create/"
    )
    PIPELINE_STATUS = build_internal_endpoint("pipeline/{pipeline_id}/status/")
    WEBHOOK_SEND = build_internal_endpoint("webhook/send/")


class WorkerConfig:
    """Worker-specific configuration - not shared with backend."""

    DEFAULT_TASK_TIMEOUT = 300
    FILE_PROCESSING_TIMEOUT = 1800
    CALLBACK_TIMEOUT = 120
    WEBHOOK_TIMEOUT = 30

    MAX_FILE_BATCH_SIZE = 20
    MAX_PARALLEL_FILE_BATCHES = 4

    API_REQUEST_TIMEOUT = 30
    CACHE_TTL = 60


class ErrorMessages:
    """Worker-specific error messages."""

    TASK_TIMEOUT = "Task execution timed out after {timeout} seconds"
    FILE_PROCESSING_FAILED = "Failed to process file {file_name}: {error}"
    API_CONNECTION_FAILED = "Failed to connect to internal API: {error}"
    WEBHOOK_DELIVERY_FAILED = "Webhook delivery failed: {error}"


# Status Mapping Utilities (Worker-Specific)
class StatusMappings:
    """Map between core domain status and worker implementation status."""

    EXECUTION_TO_PIPELINE = {
        ExecutionStatus.COMPLETED: PipelineStatus.SUCCESS,
        ExecutionStatus.ERROR: PipelineStatus.FAILURE,
        ExecutionStatus.EXECUTING: PipelineStatus.INPROGRESS,
        ExecutionStatus.PENDING: PipelineStatus.YET_TO_START,
    }

    @classmethod
    def execution_to_pipeline(cls, execution_status: ExecutionStatus) -> PipelineStatus:
        """Convert core ExecutionStatus to worker PipelineStatus."""
        return cls.EXECUTION_TO_PIPELINE.get(execution_status, PipelineStatus.FAILURE)


# Example: Worker-Specific Base Class (NOT in core)
class WorkerTaskBase:
    """Base class for worker tasks - worker implementation detail."""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def log_task_start(self, task_name: TaskName, task_id: str):
        """Worker-specific logging."""
        self.logger.info(f"Starting worker task {task_name.value} with ID {task_id}")

    def handle_worker_error(self, error: Exception, context: dict) -> dict:
        """Worker-specific error handling."""
        return {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "worker_context": context,
            "timestamp": datetime.now().isoformat(),
        }


# Demonstration
def demonstrate_separation():
    """Show the clean separation between core domain models and worker patterns."""
    print("🏗️  Architecture Separation Demo")

    # 1. Core domain model (shared with backend)
    print("\n1. Core Domain Model:")
    print(f"   ExecutionStatus.COMPLETED = {ExecutionStatus.COMPLETED}")
    print("   (Shared between backend and workers)")

    # 2. Worker-specific enums (NOT shared with backend)
    print("\n2. Worker-Specific Patterns:")
    print(f"   TaskName.PROCESS_FILE_BATCH = {TaskName.PROCESS_FILE_BATCH}")
    print(f"   QueueName.FILE_PROCESSING = {QueueName.FILE_PROCESSING}")
    print(f"   WebhookStatus.DELIVERED = {WebhookStatus.DELIVERED}")
    print("   (Worker implementation details)")

    # 3. Worker result using core status
    print("\n3. Worker Result with Core Status:")
    result = FileExecutionResult(
        file="test.pdf",
        file_execution_id="exec-123",
        status=ExecutionStatus.COMPLETED,  # Core domain model
        processing_time=1.5,
    )
    print(
        f"   File: {result.file}, Status: {result.status}, Success: {result.is_successful()}"
    )

    # 4. Status mapping between domains
    print("\n4. Status Mapping:")
    pipeline_status = StatusMappings.execution_to_pipeline(ExecutionStatus.COMPLETED)
    print(f"   Core ExecutionStatus.COMPLETED → Worker PipelineStatus.{pipeline_status}")

    print(
        "\n✅ Clean separation: Core has domain models, Workers have implementation patterns"
    )


if __name__ == "__main__":
    demonstrate_separation()
