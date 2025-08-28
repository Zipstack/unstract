"""Consistent Response Models for Workers

These models provide consistent response formats across all worker operations,
eliminating dict-based response handling and ensuring type safety.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ResponseStatus(str, Enum):
    """Standard response status values."""

    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BaseResponse:
    """Base response class for all worker operations."""

    success: bool
    message: str | None = None
    status_code: int | None = None

    @classmethod
    def success_response(
        cls, message: str | None = None, status_code: int = 200
    ) -> "BaseResponse":
        """Create a successful response."""
        return cls(success=True, message=message, status_code=status_code)

    @classmethod
    def error_response(cls, message: str, status_code: int = 400) -> "BaseResponse":
        """Create an error response."""
        return cls(success=False, message=message, status_code=status_code)


@dataclass
class APIResponse(BaseResponse):
    """Standard API response with data payload."""

    data: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert response to dictionary format for compatibility."""
        result = {
            "success": self.success,
            "data": self.data or {},
            "status_code": self.status_code,
        }
        if self.message:
            result["message"] = self.message
        if self.error:
            result["error"] = self.error
        return result

    @classmethod
    def success_response(
        cls,
        data: dict[str, Any] | None = None,
        message: str | None = None,
        status_code: int = 200,
    ) -> "APIResponse":
        """Create a successful API response."""
        return cls(success=True, data=data, message=message, status_code=status_code)

    @classmethod
    def error_response(
        cls, error: str, message: str | None = None, status_code: int = 400
    ) -> "APIResponse":
        """Create an error API response."""
        return cls(success=False, error=error, message=message, status_code=status_code)


@dataclass
class BatchOperationResponse(BaseResponse):
    """Response for batch operations."""

    successful_items: int = 0
    failed_items: int = 0
    total_items: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @classmethod
    def success_response(
        cls,
        successful_items: int,
        total_items: int,
        failed_items: int = 0,
        errors: list[str] | None = None,
        message: str | None = None,
    ) -> "BatchOperationResponse":
        """Create a successful batch response."""
        return cls(
            success=True,
            successful_items=successful_items,
            failed_items=failed_items,
            total_items=total_items,
            errors=errors or [],
            message=message,
        )

    @classmethod
    def error_response(
        cls,
        total_items: int,
        errors: list[str],
        successful_items: int = 0,
        message: str | None = None,
    ) -> "BatchOperationResponse":
        """Create an error batch response."""
        failed_items = total_items - successful_items
        return cls(
            success=False,
            successful_items=successful_items,
            failed_items=failed_items,
            total_items=total_items,
            errors=errors,
            message=message,
        )

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_items == 0:
            return 0.0
        return (self.successful_items / self.total_items) * 100.0


@dataclass
class ExecutionResponse(APIResponse):
    """Response for workflow/task execution operations."""

    execution_id: str | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def success_response(
        cls,
        execution_id: str | None = None,
        status: str = ResponseStatus.SUCCESS,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> "ExecutionResponse":
        """Create a successful execution response."""
        return cls(
            success=True,
            execution_id=execution_id,
            status=status,
            data=data,
            metadata=metadata,
            message=message,
        )

    @classmethod
    def error_response(
        cls,
        error: str,
        execution_id: str | None = None,
        status: str = ResponseStatus.ERROR,
        message: str | None = None,
    ) -> "ExecutionResponse":
        """Create an error execution response."""
        return cls(
            success=False,
            execution_id=execution_id,
            status=status,
            error=error,
            message=message,
        )


@dataclass
class WebhookResponse(APIResponse):
    """Response for webhook operations."""

    task_id: str | None = None
    url: str | None = None
    delivery_status: str | None = None

    @classmethod
    def success_response(
        cls,
        task_id: str | None = None,
        url: str | None = None,
        delivery_status: str = "delivered",
        data: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> "WebhookResponse":
        """Create a successful webhook response."""
        return cls(
            success=True,
            task_id=task_id,
            url=url,
            delivery_status=delivery_status,
            data=data,
            message=message,
        )

    @classmethod
    def error_response(
        cls,
        error: str,
        task_id: str | None = None,
        url: str | None = None,
        delivery_status: str = "failed",
        message: str | None = None,
    ) -> "WebhookResponse":
        """Create an error webhook response."""
        return cls(
            success=False,
            task_id=task_id,
            url=url,
            delivery_status=delivery_status,
            error=error,
            message=message,
        )


@dataclass
class FileOperationResponse(APIResponse):
    """Response for file operations."""

    file_id: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    processing_time: float | None = None

    @classmethod
    def success_response(
        cls,
        file_id: str | None = None,
        file_name: str | None = None,
        file_size: int | None = None,
        processing_time: float | None = None,
        data: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> "FileOperationResponse":
        """Create a successful file operation response."""
        return cls(
            success=True,
            file_id=file_id,
            file_name=file_name,
            file_size=file_size,
            processing_time=processing_time,
            data=data,
            message=message,
        )

    @classmethod
    def error_response(
        cls,
        error: str,
        file_id: str | None = None,
        file_name: str | None = None,
        message: str | None = None,
    ) -> "FileOperationResponse":
        """Create an error file operation response."""
        return cls(
            success=False,
            file_id=file_id,
            file_name=file_name,
            error=error,
            message=message,
        )


@dataclass
class ConnectorResponse(APIResponse):
    """Response for connector operations."""

    connector_id: str | None = None
    connector_type: str | None = None
    connection_status: str | None = None

    @classmethod
    def success_response(
        cls,
        connector_id: str | None = None,
        connector_type: str | None = None,
        connection_status: str = "connected",
        data: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> "ConnectorResponse":
        """Create a successful connector response."""
        return cls(
            success=True,
            connector_id=connector_id,
            connector_type=connector_type,
            connection_status=connection_status,
            data=data,
            message=message,
        )

    @classmethod
    def error_response(
        cls,
        error: str,
        connector_id: str | None = None,
        connector_type: str | None = None,
        connection_status: str = "failed",
        message: str | None = None,
    ) -> "ConnectorResponse":
        """Create an error connector response."""
        return cls(
            success=False,
            connector_id=connector_id,
            connector_type=connector_type,
            connection_status=connection_status,
            error=error,
            message=message,
        )


# Helper function to convert legacy dict responses to consistent objects
def convert_dict_response(
    response_dict: dict[str, Any], response_class: type = APIResponse
) -> APIResponse | BaseResponse:
    """Convert legacy dict response to consistent response object.

    This is a migration helper to gradually convert from dict-based responses
    to consistent response objects.

    Args:
        response_dict: Legacy dict response
        response_class: Target response class to convert to

    Returns:
        Consistent response object
    """
    if not isinstance(response_dict, dict):
        raise ValueError("Expected dict response for conversion")

    success = response_dict.get("success", True)

    if success:
        if response_class == APIResponse:
            return APIResponse.success_response(
                data=response_dict.get("data"),
                message=response_dict.get("message"),
                status_code=response_dict.get("status_code", 200),
            )
        elif response_class == BatchOperationResponse:
            return BatchOperationResponse.success_response(
                successful_items=response_dict.get("successful_items", 0),
                total_items=response_dict.get("total_items", 0),
                failed_items=response_dict.get("failed_items", 0),
                errors=response_dict.get("errors", []),
                message=response_dict.get("message"),
            )
        else:
            return response_class.success_response(
                message=response_dict.get("message"),
                status_code=response_dict.get("status_code", 200),
            )
    else:
        error = (
            response_dict.get("error")
            or response_dict.get("error_message")
            or "Unknown error"
        )
        return response_class.error_response(
            error=error,
            message=response_dict.get("message"),
            status_code=response_dict.get("status_code", 400),
        )


__all__ = [
    "ResponseStatus",
    "BaseResponse",
    "APIResponse",
    "BatchOperationResponse",
    "ExecutionResponse",
    "WebhookResponse",
    "FileOperationResponse",
    "ConnectorResponse",
    "convert_dict_response",
]
