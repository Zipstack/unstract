"""Execution context model for the executor framework.

Defines the serializable context that is dispatched to executor
workers via Celery. Used by both the workflow path (structure tool
task) and the IDE path (PromptStudioHelper).
"""

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExecutionSource(str, Enum):
    """Origin of the execution request."""

    IDE = "ide"
    TOOL = "tool"


class Operation(str, Enum):
    """Supported extraction operations.

    Maps 1-to-1 with current PromptTool HTTP endpoints.
    """

    EXTRACT = "extract"
    INDEX = "index"
    ANSWER_PROMPT = "answer_prompt"
    SINGLE_PASS_EXTRACTION = "single_pass_extraction"
    SUMMARIZE = "summarize"
    AGENTIC_EXTRACTION = "agentic_extraction"


@dataclass
class ExecutionContext:
    """Serializable execution context dispatched to executor worker.

    This is the single payload sent as a Celery task argument to
    ``execute_extraction``. It must remain JSON-serializable (no
    ORM objects, no file handles, no callables).

    Attributes:
        executor_name: Registered executor to handle this request
            (e.g. ``"legacy"``, ``"agentic_table"``).
        operation: The extraction operation to perform.
        run_id: Unique identifier for this execution run.
        execution_source: Where the request originated
            (``"ide"`` or ``"tool"``).
        organization_id: Tenant/org scope. ``None`` for public
            calls.
        executor_params: Opaque, operation-specific payload passed
            through to the executor. Must be JSON-serializable.
        request_id: Correlation ID for tracing across services.
    """

    executor_name: str
    operation: str
    run_id: str
    execution_source: str
    organization_id: str | None = None
    executor_params: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None

    def __post_init__(self) -> None:
        """Validate required fields after initialization."""
        if not self.executor_name:
            raise ValueError("executor_name is required")
        if not self.operation:
            raise ValueError("operation is required")
        if not self.run_id:
            raise ValueError("run_id is required")
        if not self.execution_source:
            raise ValueError("execution_source is required")

        # Normalize enum values to plain strings for serialization
        if isinstance(self.operation, Operation):
            self.operation = self.operation.value
        if isinstance(self.execution_source, ExecutionSource):
            self.execution_source = self.execution_source.value

        # Auto-generate request_id if not provided
        if self.request_id is None:
            self.request_id = str(uuid.uuid4())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict for Celery dispatch."""
        return {
            "executor_name": self.executor_name,
            "operation": self.operation,
            "run_id": self.run_id,
            "execution_source": self.execution_source,
            "organization_id": self.organization_id,
            "executor_params": self.executor_params,
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionContext":
        """Deserialize from a dict (e.g. Celery task argument)."""
        return cls(
            executor_name=data["executor_name"],
            operation=data["operation"],
            run_id=data["run_id"],
            execution_source=data["execution_source"],
            organization_id=data.get("organization_id"),
            executor_params=data.get("executor_params", {}),
            request_id=data.get("request_id"),
        )
