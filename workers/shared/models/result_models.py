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

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API deployment response with correct status format.

        This matches the backend's FileExecutionResult.to_json() format exactly.
        """
        # Convert ExecutionStatus to API deployment status strings
        if self.error or self.status == ExecutionStatus.ERROR:
            api_status = "Failed"  # ApiDeploymentResultStatus.FAILED
        else:
            api_status = "Success"  # ApiDeploymentResultStatus.SUCCESS

        return {
            "file": self.file,
            "file_execution_id": self.file_execution_id,
            "status": api_status,  # Use API deployment status format
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }

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


@dataclass
class WorkflowExecutionResult:
    """Comprehensive result for complete workflow execution."""

    execution_id: str
    workflow_id: str
    organization_id: str
    execution_status: ExecutionStatus
    total_files: int = 0
    successful_files: int = 0
    failed_files: int = 0
    execution_start_time: float = 0.0
    execution_end_time: float = 0.0
    total_execution_time: float = 0.0
    batch_results: list[BatchExecutionResult] = field(default_factory=list)
    final_output: dict[str, Any] | None = None
    error_summary: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def completion_percentage(self) -> float:
        """Get completion percentage of the workflow execution."""
        if self.total_files == 0:
            return 100.0
        processed = self.successful_files + self.failed_files
        return (processed / self.total_files) * 100.0

    @property
    def success_rate(self) -> float:
        """Get success rate of processed files."""
        if self.total_files == 0:
            return 100.0
        return (self.successful_files / self.total_files) * 100.0

    @property
    def is_completed(self) -> bool:
        """Check if workflow execution is completed."""
        return self.execution_status == ExecutionStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """Check if workflow execution failed."""
        return self.execution_status == ExecutionStatus.ERROR

    @property
    def is_executing(self) -> bool:
        """Check if workflow execution is in progress."""
        return self.execution_status == ExecutionStatus.EXECUTING

    @property
    def has_errors(self) -> bool:
        """Check if workflow has any failed files."""
        return self.failed_files > 0

    @property
    def batch_count(self) -> int:
        """Get the number of batches processed."""
        return len(self.batch_results)

    def add_batch_result(self, batch_result: BatchExecutionResult) -> None:
        """Add a batch processing result to the workflow."""
        self.batch_results.append(batch_result)

        # Update file counts from batch results
        self.successful_files += batch_result.successful_files
        self.failed_files += batch_result.failed_files
        self.total_execution_time += batch_result.execution_time

    def get_all_file_results(self) -> list[FileExecutionResult]:
        """Get all file results from all batches."""
        all_results = []
        for batch_result in self.batch_results:
            all_results.extend(batch_result.file_results)
        return all_results

    def get_error_summary(self) -> str:
        """Get a comprehensive error summary from all batches."""
        if not self.has_errors:
            return "No errors in workflow execution"

        error_messages = []
        for batch_result in self.batch_results:
            error_messages.extend(batch_result.errors)

        if self.error_summary:
            error_messages.append(self.error_summary)

        return "; ".join(filter(None, error_messages))

    def to_dict(self) -> dict[str, Any]:
        """Convert workflow execution result to dictionary."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowExecutionResult":
        """Create WorkflowExecutionResult from dictionary data."""
        status_str = data.get("execution_status", ExecutionStatus.ERROR.value)
        status = (
            ExecutionStatus(status_str) if isinstance(status_str, str) else status_str
        )

        batch_results = [
            BatchExecutionResult.from_dict(batch_data)
            for batch_data in data.get("batch_results", [])
        ]

        return cls(
            execution_id=data["execution_id"],
            workflow_id=data["workflow_id"],
            organization_id=data["organization_id"],
            execution_status=status,
            total_files=data.get("total_files", 0),
            successful_files=data.get("successful_files", 0),
            failed_files=data.get("failed_files", 0),
            execution_start_time=data.get("execution_start_time", 0.0),
            execution_end_time=data.get("execution_end_time", 0.0),
            total_execution_time=data.get("total_execution_time", 0.0),
            batch_results=batch_results,
            final_output=data.get("final_output"),
            error_summary=data.get("error_summary"),
            metadata=data.get("metadata"),
        )


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


def create_workflow_result_from_batches(
    execution_id: str,
    workflow_id: str,
    organization_id: str,
    batch_results: list[BatchExecutionResult],
    execution_status: ExecutionStatus = ExecutionStatus.COMPLETED,
) -> WorkflowExecutionResult:
    """Create WorkflowExecutionResult from batch results."""
    workflow_result = WorkflowExecutionResult(
        execution_id=execution_id,
        workflow_id=workflow_id,
        organization_id=organization_id,
        execution_status=execution_status,
        batch_results=batch_results,
    )

    # Calculate totals from batch results
    for batch_result in batch_results:
        workflow_result.total_files += batch_result.total_files
        workflow_result.successful_files += batch_result.successful_files
        workflow_result.failed_files += batch_result.failed_files
        workflow_result.total_execution_time += batch_result.execution_time

    return workflow_result
