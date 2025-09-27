"""Batch Operation Models

Dataclasses for batch operations to replace dict patterns.
"""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StatusUpdateRequest:
    """Request model for execution status updates."""

    execution_id: str
    status: str
    error_message: str | None = None
    execution_time: float | None = None
    total_files: int | None = None
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API calls."""
        data = {
            "execution_id": self.execution_id,
            "status": self.status,
            "updated_at": self.updated_at,
        }
        if self.error_message is not None:
            data["error_message"] = self.error_message
        if self.execution_time is not None:
            data["execution_time"] = self.execution_time
        if self.total_files is not None:
            data["total_files"] = self.total_files
        return data


@dataclass
class PipelineUpdateRequest:
    """Request model for pipeline status updates."""

    pipeline_id: str
    execution_id: str
    status: str
    last_run_status: str | None = None
    last_run_time: float | None = None
    increment_run_count: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API calls."""
        data = {
            "pipeline_id": self.pipeline_id,
            "execution_id": self.execution_id,
            "status": self.status,
            "increment_run_count": self.increment_run_count,
        }
        if self.last_run_status is not None:
            data["last_run_status"] = self.last_run_status
        if self.last_run_time is not None:
            data["last_run_time"] = self.last_run_time
        return data


@dataclass
class FileStatusUpdateRequest:
    """Request model for file execution status updates."""

    file_execution_id: str
    status: str
    result: dict[str, Any] | None = None
    error_message: str | None = None
    processing_time: float | None = None
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API calls."""
        data = {
            "file_execution_id": self.file_execution_id,
            "status": self.status,
            "updated_at": self.updated_at,
        }
        if self.result is not None:
            data["result"] = self.result
        if self.error_message is not None:
            data["error_message"] = self.error_message
        if self.processing_time is not None:
            data["processing_time"] = self.processing_time
        return data


@dataclass
class WebhookNotificationRequest:
    """Request model for webhook notifications."""

    url: str
    payload: dict[str, Any]
    notification_id: str | None = None
    headers: dict[str, str] | None = None
    timeout: int = 30
    retry_count: int = 3

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API calls."""
        data = {
            "url": self.url,
            "payload": self.payload,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
        }
        if self.notification_id is not None:
            data["notification_id"] = self.notification_id
        if self.headers is not None:
            data["headers"] = self.headers
        return data
