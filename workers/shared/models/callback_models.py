"""Callback Task Models

Dataclasses for callback task execution and aggregation.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Import shared domain models from core
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../unstract/core/src"))
from unstract.core import ExecutionStatus, serialize_dataclass_to_dict

# Import result models
from .result_models import BatchExecutionResult


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
