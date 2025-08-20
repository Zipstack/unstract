"""Scheduler Data Models for Workers

Type-safe dataclasses for scheduler operations to replace dict-based approaches.
Uses the architectural principles from @unstract/core/data_models.py
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from unstract.core.data_models import serialize_dataclass_to_dict


class ExecutionMode(str, Enum):
    """Workflow execution modes."""

    INSTANT = "INSTANT"
    QUEUE = "QUEUE"
    SCHEDULED = "SCHEDULED"


class SchedulerExecutionStatus(str, Enum):
    """Scheduler execution status values."""

    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkflowExecutionRequest:
    """Request to create a workflow execution."""

    workflow_id: str
    pipeline_id: str
    organization_id: str
    single_step: bool = False
    mode: ExecutionMode = ExecutionMode.QUEUE
    total_files: int = 0
    scheduled: bool = True

    def __post_init__(self):
        """Validate required fields."""
        if not self.workflow_id:
            raise ValueError("Workflow ID is required")
        if not self.pipeline_id:
            raise ValueError("Pipeline ID is required")
        if not self.organization_id:
            raise ValueError("Organization ID is required")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API calls."""
        return serialize_dataclass_to_dict(self)


@dataclass
class AsyncExecutionRequest:
    """Request to trigger async workflow execution."""

    execution_id: str
    workflow_id: str
    pipeline_id: str
    organization_id: str
    scheduled: bool = True
    use_file_history: bool = True
    hash_values_of_files: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate required fields."""
        if not self.execution_id:
            raise ValueError("Execution ID is required")
        if not self.workflow_id:
            raise ValueError("Workflow ID is required")
        if not self.pipeline_id:
            raise ValueError("Pipeline ID is required")
        if not self.organization_id:
            raise ValueError("Organization ID is required")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API calls."""
        return serialize_dataclass_to_dict(self)


@dataclass
class SchedulerExecutionResult:
    """Result of a scheduler execution operation."""

    status: SchedulerExecutionStatus
    execution_id: str | None = None
    workflow_id: str | None = None
    pipeline_id: str | None = None
    task_id: str | None = None
    message: str = ""
    error: str | None = None

    def __post_init__(self):
        """Ensure status is valid."""
        if not isinstance(self.status, SchedulerExecutionStatus):
            if isinstance(self.status, str):
                try:
                    self.status = SchedulerExecutionStatus(self.status)
                except ValueError:
                    raise ValueError(f"Invalid status: {self.status}")

    @property
    def is_success(self) -> bool:
        """Check if the execution was successful."""
        return self.status in [
            SchedulerExecutionStatus.SUCCESS,
            SchedulerExecutionStatus.COMPLETED,
        ]

    @property
    def is_error(self) -> bool:
        """Check if the execution failed."""
        return self.status in [
            SchedulerExecutionStatus.ERROR,
            SchedulerExecutionStatus.FAILED,
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def success(
        cls,
        execution_id: str,
        workflow_id: str | None = None,
        pipeline_id: str | None = None,
        task_id: str | None = None,
        message: str = "Execution completed successfully",
    ) -> "SchedulerExecutionResult":
        """Create a success result."""
        return cls(
            status=SchedulerExecutionStatus.SUCCESS,
            execution_id=execution_id,
            workflow_id=workflow_id,
            pipeline_id=pipeline_id,
            task_id=task_id,
            message=message,
        )

    @classmethod
    def error(
        cls,
        error: str,
        execution_id: str | None = None,
        workflow_id: str | None = None,
        pipeline_id: str | None = None,
        message: str = "Execution failed",
    ) -> "SchedulerExecutionResult":
        """Create an error result."""
        return cls(
            status=SchedulerExecutionStatus.ERROR,
            execution_id=execution_id,
            workflow_id=workflow_id,
            pipeline_id=pipeline_id,
            message=message,
            error=error,
        )


@dataclass
class ScheduledPipelineContext:
    """Context information for a scheduled pipeline execution."""

    pipeline_id: str
    pipeline_name: str
    workflow_id: str
    organization_id: str
    use_file_history: bool = True

    def __post_init__(self):
        """Validate required fields."""
        if not self.pipeline_id:
            raise ValueError("Pipeline ID is required")
        if not self.pipeline_name:
            raise ValueError("Pipeline name is required")
        if not self.workflow_id:
            raise ValueError("Workflow ID is required")
        if not self.organization_id:
            raise ValueError("Organization ID is required")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return serialize_dataclass_to_dict(self)


__all__ = [
    "ExecutionMode",
    "SchedulerExecutionStatus",
    "WorkflowExecutionRequest",
    "AsyncExecutionRequest",
    "SchedulerExecutionResult",
    "ScheduledPipelineContext",
]
