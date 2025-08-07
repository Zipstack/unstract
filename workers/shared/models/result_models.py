"""Worker Result Models

Dataclasses for task execution results.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Any

# Import shared domain models from core
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../unstract/core/src"))
from unstract.core import ExecutionStatus, serialize_dataclass_to_dict

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
        return self.status == ExecutionStatus.COMPLETED

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
