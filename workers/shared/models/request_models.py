"""API Request Models

Dataclasses for API request payloads.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Any

# Import shared domain models from core
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../unstract/core/src"))
from unstract.core import ExecutionStatus

# Import worker enums
from ..enums import NotificationMethod, PipelineStatus


@dataclass
class WorkflowExecutionUpdateRequest:
    """Request data for updating workflow execution status."""

    status: ExecutionStatus
    error_message: str | None = None
    result: dict[str, Any] | None = None
    execution_time: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        data = {"status": str(self.status)}
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
        return {
            "method": self.method.value,
            "recipients": self.recipients,
            "subject": self.subject,
            "message": self.message,
            "metadata": self.metadata,
            "priority": self.priority,
        }


@dataclass
class FileExecutionStatusUpdateRequest:
    """Request data for updating file execution status."""

    status: str
    error_message: str | None = None
    result: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        data = {"status": self.status}
        if self.error_message:
            data["error_message"] = self.error_message
        if self.result:
            data["result"] = self.result
        return data
