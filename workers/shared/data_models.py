"""Shared Data Models for Worker Services

This module contains dataclass definitions used across worker services
to ensure type safety and prevent dictionary usage for structured data.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from .enums import (
    BatchOperationType,
    CircuitBreakerState,
    ConnectionType,
    EndpointType,
    FileOperationType,
    HTTPMethod,
    LogLevel,
    NotificationPlatform,
    TaskStatus,
    ToolOutputType,
)


@dataclass
class WorkflowExecutionData:
    """Workflow execution data structure."""

    id: str | UUID
    workflow_id: str | UUID
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    execution_method: str | None = None
    total_files: int | None = None
    completed_files: int | None = None
    failed_files: int | None = None
    error_message: str | None = None
    execution_time: float | None = None
    attempts: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "workflow_id": str(self.workflow_id),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "execution_method": self.execution_method,
            "total_files": self.total_files,
            "completed_files": self.completed_files,
            "failed_files": self.failed_files,
            "error_message": self.error_message,
            "execution_time": self.execution_time,
            "attempts": self.attempts,
        }


@dataclass
class WorkflowDefinition:
    """Workflow definition data structure."""

    id: str | UUID
    workflow_name: str
    workflow_type: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "workflow_name": self.workflow_name,
            "workflow_type": self.workflow_type,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class FileExecutionData:
    """File execution data structure."""

    id: str | UUID
    workflow_execution_id: str | UUID
    file_path: str
    file_name: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    file_size: int | None = None
    mime_type: str | None = None
    file_hash: str | None = None
    processing_time: float | None = None
    error_message: str | None = None
    result_data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "workflow_execution_id": str(self.workflow_execution_id),
            "file_path": self.file_path,
            "file_name": self.file_name,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "file_hash": self.file_hash,
            "processing_time": self.processing_time,
            "error_message": self.error_message,
            "result_data": self.result_data,
        }


@dataclass
class ToolExecutionData:
    """Tool execution data structure."""

    id: str | UUID
    tool_name: str
    tool_version: str
    status: TaskStatus
    output_type: ToolOutputType
    created_at: datetime
    updated_at: datetime
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    execution_time: float | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "status": self.status.value,
            "output_type": self.output_type.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "input_data": self.input_data,
            "output_data": self.output_data,
            "execution_time": self.execution_time,
            "error_message": self.error_message,
        }


@dataclass
class WebhookDeliveryData:
    """Webhook delivery data structure."""

    id: str | UUID
    url: str
    method: HTTPMethod
    platform: NotificationPlatform
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    payload: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    response_code: int | None = None
    response_data: dict[str, Any] | None = None
    attempts: int | None = None
    next_retry_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "url": self.url,
            "method": self.method.value,
            "platform": self.platform.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "payload": self.payload,
            "headers": self.headers,
            "response_code": self.response_code,
            "response_data": self.response_data,
            "attempts": self.attempts,
            "next_retry_at": self.next_retry_at.isoformat()
            if self.next_retry_at
            else None,
        }


@dataclass
class EndpointConfiguration:
    """Endpoint configuration data structure."""

    id: str | UUID
    endpoint_type: EndpointType
    connection_type: ConnectionType
    configuration: dict[str, Any]
    name: str | None = None
    description: str | None = None
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "endpoint_type": self.endpoint_type.value,
            "connection_type": self.connection_type.value,
            "configuration": self.configuration,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
        }


@dataclass
class BatchOperationRequest:
    """Batch operation request data structure."""

    operation_type: BatchOperationType
    items: list[dict[str, Any]]
    organization_id: str | None = None
    batch_size: int = 100
    parallel_processing: bool = True

    def to_dict(self) -> dict[str, Any]:
        # Use 'updates' field name for status update operations to match backend API
        items_field_name = (
            "updates"
            if self.operation_type == BatchOperationType.STATUS_UPDATE
            else "items"
        )

        return {
            "operation_type": self.operation_type.value,
            items_field_name: self.items,
            "organization_id": self.organization_id,
            "batch_size": self.batch_size,
            "parallel_processing": self.parallel_processing,
        }


@dataclass
class BatchOperationResponse:
    """Batch operation response data structure."""

    operation_id: str
    total_items: int
    successful_items: int
    failed_items: int
    status: TaskStatus
    results: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    execution_time: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "total_items": self.total_items,
            "successful_items": self.successful_items,
            "failed_items": self.failed_items,
            "status": self.status.value,
            "results": self.results,
            "errors": self.errors,
            "execution_time": self.execution_time,
        }


@dataclass
class FileHistoryData:
    """File history data structure."""

    id: str | UUID
    file_execution_id: str | UUID
    operation_type: FileOperationType
    timestamp: datetime
    file_path: str
    file_name: str
    file_size: int | None = None
    status: TaskStatus | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "file_execution_id": str(self.file_execution_id),
            "operation_type": self.operation_type.value,
            "timestamp": self.timestamp.isoformat(),
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "status": self.status.value if self.status else None,
            "metadata": self.metadata,
        }


@dataclass
class CircuitBreakerStatus:
    """Circuit breaker status data structure."""

    state: CircuitBreakerState
    failure_count: int
    last_failure_time: datetime | None = None
    next_attempt_time: datetime | None = None
    success_count: int = 0
    total_requests: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time.isoformat()
            if self.last_failure_time
            else None,
            "next_attempt_time": self.next_attempt_time.isoformat()
            if self.next_attempt_time
            else None,
            "success_count": self.success_count,
            "total_requests": self.total_requests,
        }


@dataclass
class LogEntry:
    """Log entry data structure."""

    timestamp: datetime
    level: LogLevel
    message: str
    logger_name: str
    module: str | None = None
    function: str | None = None
    line_number: int | None = None
    context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "message": self.message,
            "logger_name": self.logger_name,
            "module": self.module,
            "function": self.function,
            "line_number": self.line_number,
            "context": self.context,
        }


@dataclass
class APIResponse:
    """Generic API response data structure."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    status_code: int | None = None
    timestamp: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "status_code": self.status_code,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class StatusUpdateRequest:
    """Status update request data structure."""

    id: str | UUID
    status: TaskStatus
    error_message: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "status": self.status.value,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class MetricsData:
    """Metrics data structure."""

    timestamp: datetime
    metric_name: str
    value: int | float
    unit: str
    tags: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "tags": self.tags,
        }


# Utility functions for data model conversion
def dict_to_dataclass(data: dict[str, Any], dataclass_type):
    """Convert dictionary to dataclass instance."""
    if not isinstance(data, dict):
        return data

    # Get field names and types from dataclass
    from dataclasses import fields

    if not hasattr(dataclass_type, "__dataclass_fields__"):
        return data

    field_types = {field.name: field.type for field in fields(dataclass_type)}
    kwargs = {}

    for field_name, field_type in field_types.items():
        if field_name in data:
            value = data[field_name]

            # Handle datetime conversion
            if field_type == datetime and isinstance(value, str):
                kwargs[field_name] = datetime.fromisoformat(value.replace("Z", "+00:00"))
            # Handle UUID conversion
            elif field_type in [UUID, str | UUID] and isinstance(value, str):
                kwargs[field_name] = value
            # Handle enum conversion
            elif hasattr(field_type, "__bases__") and any(
                base.__name__ == "Enum" for base in field_type.__bases__
            ):
                kwargs[field_name] = field_type(value)
            else:
                kwargs[field_name] = value

    return dataclass_type(**kwargs)
