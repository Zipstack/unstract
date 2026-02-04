"""Worker Result Models

Dataclasses for task execution results.
"""

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# Import shared domain models from core
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../unstract/core/src"))
from shared.enums import QueueResultStatus

from unstract.core import ExecutionStatus, serialize_dataclass_to_dict
from unstract.core.worker_models import FileExecutionResult

# Import worker enums
from ..enums import WebhookStatus


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
class CallbackProcessingResult:
    """Result for callback processing operations."""

    callback_id: str
    execution_id: str
    organization_id: str
    workflow_id: str
    results: list[dict[str, Any]] = field(default_factory=list)
    callback_status: ExecutionStatus = ExecutionStatus.COMPLETED
    processing_time: float = 0.0
    successful_callbacks: int = 0
    failed_callbacks: int = 0
    error_message: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def result_count(self) -> int:
        """Get the number of results in this callback."""
        return len(self.results) if self.results else 0

    @property
    def has_results(self) -> bool:
        """Check if this callback has any results."""
        return self.result_count > 0

    @property
    def is_successful(self) -> bool:
        """Check if callback processing was successful."""
        return (
            self.callback_status == ExecutionStatus.COMPLETED and not self.error_message
        )

    def get_successful_results(self) -> list[dict[str, Any]]:
        """Filter and return only successful results."""
        if not self.results:
            return []

        return [
            result
            for result in self.results
            if isinstance(result, dict) and not result.get("error")
        ]

    def get_failed_results(self) -> list[dict[str, Any]]:
        """Filter and return only failed results."""
        if not self.results:
            return []

        return [
            result
            for result in self.results
            if isinstance(result, dict) and result.get("error")
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert callback result to dictionary."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CallbackProcessingResult":
        """Create CallbackProcessingResult from dictionary data."""
        status_str = data.get("callback_status", ExecutionStatus.COMPLETED.value)
        status = (
            ExecutionStatus(status_str) if isinstance(status_str, str) else status_str
        )

        return cls(
            callback_id=data["callback_id"],
            execution_id=data["execution_id"],
            organization_id=data["organization_id"],
            workflow_id=data["workflow_id"],
            results=data.get("results", []),
            callback_status=status,
            processing_time=data.get("processing_time", 0.0),
            successful_callbacks=data.get("successful_callbacks", 0),
            failed_callbacks=data.get("failed_callbacks", 0),
            error_message=data.get("error_message"),
            metadata=data.get("metadata"),
        )


# Utility functions for result aggregation
def aggregate_file_results(
    file_results: list[FileExecutionResult],
) -> BatchExecutionResult:
    """Aggregate multiple file results into a batch result."""
    successful = len([r for r in file_results if r.is_successful()])
    failed = len([r for r in file_results if r.has_error()])
    total_time = sum(r.processing_time for r in file_results)

    return BatchExecutionResult(
        total_files=len(file_results),
        successful_files=successful,
        failed_files=failed,
        execution_time=total_time,
        file_results=file_results,
    )


@dataclass
class QueueResult:
    file: str
    status: QueueResultStatus
    result: Any
    workflow_id: str
    file_content: str | None = None
    whisper_hash: str | None = None
    file_execution_id: str | None = None
    enqueued_at: float | None = None
    ttl_seconds: int | None = None
    extracted_text: str | None = None
    hitl_reason: str | None = None
    hitl_queue_name: str | None = None

    def __post_init__(self):
        """Initialize enqueued_at timestamp if not provided and validate required fields"""
        if self.enqueued_at is None:
            self.enqueued_at = time.time()

        # Validate required fields
        if not self.file:
            raise ValueError("QueueResult requires a valid file name")
        if not self.workflow_id:
            raise ValueError("QueueResult requires a valid workflow_id")
        if self.status is None:
            raise ValueError("QueueResult requires a valid status")

    def to_dict(self) -> Any:
        result_dict = {
            "file": self.file,
            "whisper_hash": self.whisper_hash,
            "status": self.status.value,
            "result": self.result,
            "workflow_id": self.workflow_id,
            "file_content": self.file_content,
            "file_execution_id": self.file_execution_id,
            "enqueued_at": self.enqueued_at,
            "ttl_seconds": self.ttl_seconds,
            "extracted_text": self.extracted_text,
            "hitl_reason": self.hitl_reason,
            "hitl_queue_name": self.hitl_queue_name,
        }
        return result_dict
