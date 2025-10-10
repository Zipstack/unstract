"""API Response Data Models

This module provides strongly-typed dataclasses for API responses,
replacing fragile dictionary-based response handling with type-safe structures.
"""

# Import shared domain models from core
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../unstract/core/src"))
from unstract.core.data_models import ExecutionStatus

from ..enums import PipelineType


@dataclass
class BaseAPIResponse:
    """Base class for all API responses with common fields."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    status_code: int | None = None
    timestamp: datetime | None = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def is_successful(self) -> bool:
        """Check if the response was successful."""
        return self.success and not self.error

    @property
    def has_data(self) -> bool:
        """Check if the response contains data."""
        return bool(self.data)

    def get_data_field(self, field_name: str, default: Any = None) -> Any:
        """Safely get a field from response data."""
        if not self.data:
            return default
        return self.data.get(field_name, default)

    def to_dict(self) -> dict[str, Any]:
        """Convert response to dictionary for serialization."""
        result = {
            "success": self.success,
            "status_code": self.status_code,
        }

        if self.data is not None:
            result["data"] = self.data

        if self.error:
            result["error"] = self.error

        if self.timestamp:
            result["timestamp"] = self.timestamp.isoformat()

        return result


@dataclass
class WorkflowExecutionResponse(BaseAPIResponse):
    """Response from workflow execution API calls."""

    execution_id: str | None = None
    workflow_id: str | None = None
    status: str | None = None
    execution_time: float | None = None
    total_files: int | None = None
    completed_files: int | None = None
    failed_files: int | None = None

    @classmethod
    def from_api_response(cls, response: dict[str, Any]) -> "WorkflowExecutionResponse":
        """Create from raw API response dictionary."""
        data = response.get("data", {})
        execution = data.get("execution", {})

        return cls(
            success=response.get("success", False),
            data=data,
            error=response.get("error"),
            status_code=response.get("status_code"),
            execution_id=execution.get("id") or data.get("execution_id"),
            workflow_id=execution.get("workflow_id") or data.get("workflow_id"),
            status=execution.get("status") or data.get("status"),
            execution_time=execution.get("execution_time"),
            total_files=execution.get("total_files"),
            completed_files=execution.get("completed_files"),
            failed_files=execution.get("failed_files"),
        )

    @property
    def is_completed(self) -> bool:
        """Check if execution is completed."""
        return self.status == ExecutionStatus.COMPLETED.value

    @property
    def is_failed(self) -> bool:
        """Check if execution failed."""
        return self.status == ExecutionStatus.ERROR.value

    @property
    def is_executing(self) -> bool:
        """Check if execution is in progress."""
        return self.status == ExecutionStatus.EXECUTING.value


@dataclass
class FileExecutionResponse(BaseAPIResponse):
    """Response from file execution API calls."""

    file_execution_id: str | None = None
    file_name: str | None = None
    file_path: str | None = None
    file_hash: str | None = None
    status: str | None = None
    processing_time: float | None = None
    error_message: str | None = None
    result_data: dict[str, Any] | None = None

    @classmethod
    def from_api_response(cls, response: dict[str, Any]) -> "FileExecutionResponse":
        """Create from raw API response dictionary."""
        data = response.get("data", {})

        return cls(
            success=response.get("success", False),
            data=data,
            error=response.get("error"),
            status_code=response.get("status_code"),
            file_execution_id=data.get("id") or data.get("file_execution_id"),
            file_name=data.get("file_name"),
            file_path=data.get("file_path"),
            file_hash=data.get("file_hash"),
            status=data.get("status"),
            processing_time=data.get("processing_time") or data.get("execution_time"),
            error_message=data.get("error_message"),
            result_data=data.get("result_data") or data.get("result"),
        )

    @property
    def is_successful(self) -> bool:
        """Check if file execution was successful."""
        return self.success and self.status == ExecutionStatus.COMPLETED.value


@dataclass
class WorkflowEndpointsResponse(BaseAPIResponse):
    """Response from workflow endpoints API calls."""

    endpoints: list[dict[str, Any]] = field(default_factory=list)
    has_api_endpoints: bool = False
    source_endpoint: dict[str, Any] | None = None
    destination_endpoint: dict[str, Any] | None = None

    @classmethod
    def from_api_response(
        cls, response: dict[str, Any] | list
    ) -> "WorkflowEndpointsResponse":
        """Create from raw API response (handles both dict and list formats)."""
        # Handle new enhanced format (dict)
        if isinstance(response, dict):
            return cls(
                success=response.get("success", True),
                data=response,
                endpoints=response.get("endpoints", []),
                has_api_endpoints=response.get("has_api_endpoints", False),
                source_endpoint=cls._find_endpoint(
                    response.get("endpoints", []), "SOURCE"
                ),
                destination_endpoint=cls._find_endpoint(
                    response.get("endpoints", []), "DESTINATION"
                ),
            )
        # Handle legacy format (list)
        elif isinstance(response, list):
            return cls(
                success=True,
                data={"endpoints": response},
                endpoints=response,
                has_api_endpoints=len(response) > 0,
                source_endpoint=cls._find_endpoint(response, "SOURCE"),
                destination_endpoint=cls._find_endpoint(response, "DESTINATION"),
            )
        else:
            return cls(
                success=False,
                error=f"Invalid response type: {type(response)}",
            )

    @staticmethod
    def _find_endpoint(
        endpoints: list[dict[str, Any]], endpoint_type: str
    ) -> dict[str, Any] | None:
        """Find endpoint by type."""
        for endpoint in endpoints:
            if endpoint.get("endpoint_type") == endpoint_type:
                return endpoint
        return None

    @property
    def source_connection_type(self) -> str | None:
        """Get source connection type."""
        if self.source_endpoint:
            return self.source_endpoint.get("connection_type")
        return None

    @property
    def destination_connection_type(self) -> str | None:
        """Get destination connection type."""
        if self.destination_endpoint:
            return self.destination_endpoint.get("connection_type")
        return None

    @property
    def is_api_workflow(self) -> bool:
        """Check if this is an API workflow."""
        return self.has_api_endpoints or self.source_connection_type == "API"


@dataclass
class FileBatchResponse(BaseAPIResponse):
    """Response from file batch creation API calls."""

    batch_id: str | None = None
    total_files: int = 0
    created_files: list[dict[str, Any]] = field(default_factory=list)
    execution_id: str | None = None
    workflow_id: str | None = None

    @classmethod
    def from_api_response(cls, response: dict[str, Any]) -> "FileBatchResponse":
        """Create from raw API response dictionary."""
        data = response.get(
            "data", response
        )  # Handle both wrapped and unwrapped responses

        return cls(
            success=response.get("success", True),
            data=data,
            error=response.get("error"),
            status_code=response.get("status_code"),
            batch_id=data.get("batch_id"),
            total_files=data.get("total_files", 0),
            created_files=data.get("created_files", []),
            execution_id=data.get("execution_id"),
            workflow_id=data.get("workflow_id"),
        )

    @property
    def file_count(self) -> int:
        """Get the number of files in the batch."""
        return len(self.created_files)


@dataclass
class ToolExecutionResponse(BaseAPIResponse):
    """Response from tool execution API calls."""

    tool_id: str | None = None
    tool_name: str | None = None
    execution_result: dict[str, Any] | None = None
    execution_time: float | None = None
    step: int | None = None

    @classmethod
    def from_api_response(cls, response: dict[str, Any]) -> "ToolExecutionResponse":
        """Create from raw API response dictionary."""
        data = response.get("data", {})

        return cls(
            success=response.get("success", False),
            data=data,
            error=response.get("error") or data.get("error_message"),
            status_code=response.get("status_code"),
            tool_id=data.get("tool_id"),
            tool_name=data.get("tool_name") or data.get("tool_function"),
            execution_result=data.get("execution_result") or data.get("output"),
            execution_time=data.get("execution_time"),
            step=data.get("step"),
        )


@dataclass
class FileHistoryResponse(BaseAPIResponse):
    """Response from file history API calls."""

    found: bool = False
    file_history: dict[str, Any] | None = None
    is_completed: bool = False
    cached_result: dict[str, Any] | None = None

    @classmethod
    def from_api_response(cls, response: dict[str, Any]) -> "FileHistoryResponse":
        """Create from raw API response dictionary."""
        data = response.get("data", response)
        file_history = data.get("file_history")

        # Determine if file was found in history
        found = bool(file_history)
        is_completed = False

        if file_history:
            if isinstance(file_history, dict):
                is_completed = (
                    file_history.get("is_completed", False)
                    or file_history.get("status") == "COMPLETED"
                )
            elif isinstance(file_history, list) and len(file_history) > 0:
                # Check if any history record is completed
                for record in file_history:
                    if (
                        record.get("is_completed", False)
                        or record.get("status") == "COMPLETED"
                    ):
                        is_completed = True
                        break

        return cls(
            success=response.get("success", True),
            data=data,
            error=response.get("error"),
            found=found,
            file_history=file_history,
            is_completed=is_completed,
            cached_result=data.get("cached_result") or data.get("result"),
        )


@dataclass
class ManualReviewResponse(BaseAPIResponse):
    """Response from manual review API calls."""

    q_file_no_list: list[int] = field(default_factory=list)
    total_files_for_review: int = 0
    review_rules: dict[str, Any] | None = None

    @classmethod
    def from_api_response(cls, response: dict[str, Any]) -> "ManualReviewResponse":
        """Create from raw API response dictionary."""
        data = response.get("data", {})

        return cls(
            success=response.get("success", False),
            data=data,
            error=response.get("error"),
            q_file_no_list=data.get("q_file_no_list", []),
            total_files_for_review=len(data.get("q_file_no_list", [])),
            review_rules=data.get("review_rules"),
        )

    @property
    def has_files_for_review(self) -> bool:
        """Check if there are files marked for manual review."""
        return self.total_files_for_review > 0


@dataclass
class WorkflowDefinitionResponse(BaseAPIResponse):
    """Response from workflow definition API calls."""

    workflow_id: str | None = None
    workflow_name: str | None = None
    workflow_type: str | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] | None = None

    @classmethod
    def from_api_response(cls, response: dict[str, Any]) -> "WorkflowDefinitionResponse":
        """Create from raw API response dictionary."""
        data = response.get("data", response)

        return cls(
            success=response.get("success", True),
            data=data,
            error=response.get("error"),
            workflow_id=data.get("workflow_id") or data.get("id"),
            workflow_name=data.get("workflow_name") or data.get("name"),
            workflow_type=data.get("workflow_type") or data.get("type"),
            tools=data.get("tools", []),
            settings=data.get("settings"),
        )

    @property
    def pipeline_type(self) -> PipelineType | None:
        """Get the workflow type as a PipelineType enum."""
        if self.workflow_type:
            try:
                return PipelineType(self.workflow_type.upper())
            except ValueError:
                return None
        return None

    @property
    def tool_count(self) -> int:
        """Get the number of tools in the workflow."""
        return len(self.tools)


@dataclass
class ToolInstancesResponse(BaseAPIResponse):
    """Response from tool instances API calls."""

    tool_instances: list[dict[str, Any]] = field(default_factory=list)
    workflow_id: str | None = None

    @classmethod
    def from_api_response(cls, response: dict[str, Any]) -> "ToolInstancesResponse":
        """Create from raw API response dictionary."""
        data = response.get("data", response)

        return cls(
            success=response.get("success", True),
            data=data,
            error=response.get("error"),
            tool_instances=data.get("tool_instances", []),
            workflow_id=data.get("workflow_id"),
        )

    @property
    def has_tools(self) -> bool:
        """Check if there are any tool instances."""
        return len(self.tool_instances) > 0

    def get_tools_by_step(self) -> list[dict[str, Any]]:
        """Get tool instances sorted by step number."""
        return sorted(self.tool_instances, key=lambda t: t.get("step", 0))


# Utility functions for converting API responses
def parse_api_response(response: Any, response_class: type) -> BaseAPIResponse:
    """Parse an API response into the appropriate dataclass.

    Args:
        response: Raw API response (dict, list, or other)
        response_class: The dataclass type to parse into

    Returns:
        Instance of the specified response class
    """
    if hasattr(response_class, "from_api_response"):
        return response_class.from_api_response(response)
    else:
        # Fallback to base response
        if isinstance(response, dict):
            return BaseAPIResponse(
                success=response.get("success", False),
                data=response.get("data"),
                error=response.get("error"),
                status_code=response.get("status_code"),
            )
        else:
            return BaseAPIResponse(
                success=False,
                error=f"Cannot parse response of type {type(response)}",
            )
