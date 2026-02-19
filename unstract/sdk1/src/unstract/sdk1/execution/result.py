"""Execution result model for the executor framework.

Defines the standardized result returned by executors via the
Celery result backend. All executors must return an
``ExecutionResult`` so that callers (structure tool task,
PromptStudioHelper) have a uniform interface.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionResult:
    """Standardized result from an executor.

    Returned via the Celery result backend as a JSON dict.

    Attributes:
        success: Whether the execution completed without error.
        data: Operation-specific output payload. The shape depends
            on the operation (see response contract in the
            migration plan).
        metadata: Auxiliary information such as token usage,
            timings, or adapter metrics.
        error: Human-readable error message when ``success`` is
            ``False``. ``None`` on success.
    """

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def __post_init__(self) -> None:
        """Validate result consistency after initialization."""
        if not self.success and not self.error:
            raise ValueError(
                "error message is required when success is False"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict for Celery."""
        result: dict[str, Any] = {
            "success": self.success,
            "data": self.data,
            "metadata": self.metadata,
        }
        if self.error is not None:
            result["error"] = self.error
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionResult":
        """Deserialize from a dict (e.g. Celery result backend)."""
        return cls(
            success=data["success"],
            data=data.get("data", {}),
            metadata=data.get("metadata", {}),
            error=data.get("error"),
        )

    @classmethod
    def failure(
        cls,
        error: str,
        metadata: dict[str, Any] | None = None,
    ) -> "ExecutionResult":
        """Convenience factory for a failed result."""
        return cls(
            success=False,
            error=error,
            metadata=metadata or {},
        )
