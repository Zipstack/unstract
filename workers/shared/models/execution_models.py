"""Execution Context Models for Worker Operations

This module provides strongly-typed dataclasses for workflow execution contexts,
replacing fragile dictionary-based parameter passing with type-safe structures.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

# Import shared domain models from core
from unstract.core.data_models import ExecutionStatus, serialize_dataclass_to_dict

# Avoid circular imports by using TYPE_CHECKING
if TYPE_CHECKING:
    from ..api_client import InternalAPIClient

from ..enums import PipelineType


@dataclass
class WorkflowExecutionContext:
    """Strongly-typed context for workflow execution operations.

    Replaces dictionary-based context passing with type-safe dataclass
    that provides validation, autocomplete, and clear documentation.
    """

    files: dict[str, Any]
    workflow_id: str
    execution_id: str
    api_client: "InternalAPIClient"
    workflow_type: str
    is_api_workflow: bool
    organization_id: str | None = None
    pipeline_id: str | None = None
    use_file_history: bool | None = False
    scheduled: bool | None = False

    def __post_init__(self):
        """Validate required fields and normalize data after initialization."""
        if not self.workflow_id:
            raise ValueError("workflow_id is required for workflow execution")

        if not self.execution_id:
            raise ValueError("execution_id is required for workflow execution")

        if not self.files:
            raise ValueError("files dictionary cannot be empty")

        # Normalize workflow_type to ensure consistency
        if self.workflow_type:
            self.workflow_type = self.workflow_type.upper()

        # Validate workflow_type against known types
        valid_types = {pt.value for pt in PipelineType}
        if self.workflow_type not in valid_types:
            raise ValueError(
                f"Invalid workflow_type '{self.workflow_type}'. "
                f"Must be one of: {valid_types}"
            )

    @property
    def file_count(self) -> int:
        """Get the number of files in this execution context."""
        return len(self.files) if self.files else 0

    @property
    def is_scheduled_execution(self) -> bool:
        """Check if this is a scheduled execution."""
        return bool(self.scheduled)

    @property
    def pipeline_type_enum(self) -> PipelineType:
        """Get the workflow type as a PipelineType enum."""
        return PipelineType(self.workflow_type)

    def validate_for_api_workflow(self) -> None:
        """Validate context for API workflow requirements."""
        if self.is_api_workflow and not self.pipeline_id:
            raise ValueError("API workflows require pipeline_id")

    def validate_for_file_processing(self) -> None:
        """Validate context for file processing requirements."""
        if not self.files:
            raise ValueError("File processing requires non-empty files dictionary")

        if self.file_count == 0:
            raise ValueError("File processing requires at least one file")


@dataclass
class FileProcessingBatch:
    """Strongly-typed batch of files for processing.

    Represents a batch of files that will be processed together,
    with metadata about the batch and processing context.
    """

    batch_index: int
    files: dict[str, Any]
    execution_context: WorkflowExecutionContext
    total_batches: int
    queue_name: str

    def __post_init__(self):
        """Validate batch data after initialization."""
        if self.batch_index < 0:
            raise ValueError("batch_index cannot be negative")

        if self.total_batches <= 0:
            raise ValueError("total_batches must be positive")

        if self.batch_index >= self.total_batches:
            raise ValueError("batch_index cannot be >= total_batches")

        if not self.files:
            raise ValueError("Batch files cannot be empty")

        if not self.queue_name:
            raise ValueError("queue_name is required for batch processing")

    @property
    def batch_size(self) -> int:
        """Get the number of files in this batch."""
        return len(self.files)

    @property
    def is_final_batch(self) -> bool:
        """Check if this is the final batch in the sequence."""
        return self.batch_index == (self.total_batches - 1)

    @property
    def batch_progress(self) -> str:
        """Get human-readable batch progress string."""
        return f"Batch {self.batch_index + 1}/{self.total_batches}"


@dataclass
class CallbackExecutionContext:
    """Strongly-typed context for callback execution operations.

    Provides type-safe structure for callback task parameters,
    replacing dictionary-based parameter passing.
    """

    execution_id: str
    organization_id: str
    workflow_id: str
    results: list
    pipeline_id: str | None = None
    callback_type: str = "batch_callback"

    def __post_init__(self):
        """Validate callback context after initialization."""
        if not self.execution_id:
            raise ValueError("execution_id is required for callback execution")

        if not self.organization_id:
            raise ValueError("organization_id is required for callback execution")

        if not self.workflow_id:
            raise ValueError("workflow_id is required for callback execution")

        if self.results is None:
            raise ValueError("results list is required (can be empty)")

    @property
    def result_count(self) -> int:
        """Get the number of results in this callback."""
        return len(self.results) if self.results else 0

    @property
    def has_results(self) -> bool:
        """Check if this callback has any results."""
        return self.result_count > 0

    def get_successful_results(self) -> list:
        """Filter and return only successful results."""
        if not self.results:
            return []

        return [
            result
            for result in self.results
            if isinstance(result, dict) and not result.get("error")
        ]

    def get_failed_results(self) -> list:
        """Filter and return only failed results."""
        if not self.results:
            return []

        return [
            result
            for result in self.results
            if isinstance(result, dict) and result.get("error")
        ]


@dataclass
class TaskExecutionResult:
    """Strongly-typed result from task execution operations.

    Standardizes task result format across all workers with
    type safety and validation.
    """

    execution_id: str
    status: str
    files_processed: int
    success: bool
    error_message: str | None = None
    result_data: dict[str, Any] | None = None
    execution_time_seconds: float | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        """Validate result data after initialization."""
        if not self.execution_id:
            raise ValueError("execution_id is required for task results")

        if not self.status:
            raise ValueError("status is required for task results")

        if self.files_processed < 0:
            raise ValueError("files_processed cannot be negative")

        # If success is False, error_message should be provided
        if not self.success and not self.error_message:
            raise ValueError("error_message required when success=False")

    @property
    def is_successful(self) -> bool:
        """Check if the task execution was successful."""
        return self.success and not self.error_message

    @property
    def has_results(self) -> bool:
        """Check if the task produced result data."""
        return bool(self.result_data)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for serialization."""
        result = {
            "execution_id": self.execution_id,
            "status": self.status,
            "files_processed": self.files_processed,
            "success": self.success,
        }

        if self.error_message:
            result["error_message"] = self.error_message

        if self.result_data:
            result["result_data"] = self.result_data

        if self.execution_time_seconds is not None:
            result["execution_time_seconds"] = self.execution_time_seconds

        if self.metadata:
            result["metadata"] = self.metadata

        return result


# Utility functions for converting from existing dictionary patterns
def create_execution_context_from_dict(
    context_dict: dict[str, Any],
) -> WorkflowExecutionContext:
    """Convert dictionary-based context to strongly-typed dataclass.

    Provides migration path from existing dictionary-based patterns
    to type-safe dataclass approach.

    Args:
        context_dict: Dictionary containing execution context data

    Returns:
        WorkflowExecutionContext dataclass instance

    Raises:
        ValueError: If required fields are missing from dictionary
    """
    required_fields = [
        "files",
        "workflow_id",
        "execution_id",
        "api_client",
        "workflow_type",
        "is_api_workflow",
    ]
    missing_fields = [field for field in required_fields if field not in context_dict]

    if missing_fields:
        raise ValueError(f"Missing required context fields: {missing_fields}")

    return WorkflowExecutionContext(
        files=context_dict["files"],
        workflow_id=context_dict["workflow_id"],
        execution_id=context_dict["execution_id"],
        api_client=context_dict["api_client"],
        workflow_type=context_dict["workflow_type"],
        is_api_workflow=context_dict["is_api_workflow"],
        organization_id=context_dict.get("organization_id"),
        pipeline_id=context_dict.get("pipeline_id"),
        use_file_history=context_dict.get("use_file_history", False),
        scheduled=context_dict.get("scheduled", False),
    )


def create_callback_context_from_kwargs(
    kwargs: dict[str, Any],
) -> CallbackExecutionContext:
    """Convert kwargs dictionary to strongly-typed callback context.

    Args:
        kwargs: Keyword arguments from callback task

    Returns:
        CallbackExecutionContext dataclass instance
    """
    return CallbackExecutionContext(
        execution_id=kwargs["execution_id"],
        organization_id=kwargs["organization_id"],
        workflow_id=kwargs["workflow_id"],
        results=kwargs.get("results", []),
        pipeline_id=kwargs.get("pipeline_id"),
        callback_type=kwargs.get("callback_type", "batch_callback"),
    )


@dataclass
class WorkerOrganizationContext:
    """Worker-specific organization context with API client integration.

    Extends the basic organization context from core with worker-specific
    functionality including API client integration.
    Note: For basic organization context, use unstract.core.data_models.OrganizationContext
    """

    organization_id: str
    api_client: "InternalAPIClient"
    organization_data: dict[str, Any] | None = None
    cached_at: str | None = None

    def __post_init__(self):
        """Validate organization context after initialization."""
        if not self.organization_id:
            raise ValueError("organization_id is required for organization context")

        if not self.api_client:
            raise ValueError("api_client is required for organization context")

    @property
    def is_cached(self) -> bool:
        """Check if organization data is cached."""
        return bool(self.organization_data and self.cached_at)

    def get_organization_setting(self, setting_key: str, default: Any = None) -> Any:
        """Get organization-specific setting value."""
        if not self.organization_data:
            return default

        return self.organization_data.get("settings", {}).get(setting_key, default)


@dataclass
class WorkflowContextData:
    """Strongly-typed workflow context data.

    Replaces dictionary-based workflow context with type-safe structure
    containing all workflow execution metadata.
    """

    workflow_id: str
    workflow_name: str
    workflow_type: str
    execution_id: str
    organization_context: WorkerOrganizationContext
    files: dict[str, Any]
    settings: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    is_scheduled: bool = False

    def __post_init__(self):
        """Validate workflow context after initialization."""
        if not self.workflow_id:
            raise ValueError("workflow_id is required for workflow context")

        if not self.execution_id:
            raise ValueError("execution_id is required for workflow context")

        if not self.workflow_name:
            raise ValueError("workflow_name is required for workflow context")

        if not self.workflow_type:
            raise ValueError("workflow_type is required for workflow context")

        # Normalize workflow_type
        self.workflow_type = self.workflow_type.upper()

        # Validate workflow_type
        valid_types = {pt.value for pt in PipelineType}
        if self.workflow_type not in valid_types:
            raise ValueError(
                f"Invalid workflow_type '{self.workflow_type}'. "
                f"Must be one of: {valid_types}"
            )

    @property
    def file_count(self) -> int:
        """Get the number of files in this workflow context."""
        return len(self.files) if self.files else 0

    @property
    def pipeline_type_enum(self) -> PipelineType:
        """Get the workflow type as a PipelineType enum."""
        return PipelineType(self.workflow_type)

    @property
    def is_api_workflow(self) -> bool:
        """Check if this is an API workflow."""
        return self.pipeline_type_enum == PipelineType.API

    def get_setting(self, setting_key: str, default: Any = None) -> Any:
        """Get workflow-specific setting value."""
        if not self.settings:
            return default

        return self.settings.get(setting_key, default)

    def get_metadata(self, metadata_key: str, default: Any = None) -> Any:
        """Get workflow metadata value."""
        if not self.metadata:
            return default

        return self.metadata.get(metadata_key, default)


@dataclass
class ExecutionStatusUpdate:
    """Strongly-typed execution status update.

    Provides type-safe structure for workflow execution status updates
    with validation and consistency checks.
    """

    execution_id: str
    status: str
    organization_id: str | None = None
    workflow_id: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = None
    timestamp: str | None = None

    def __post_init__(self):
        """Validate status update after initialization."""
        if not self.execution_id:
            raise ValueError("execution_id is required for status update")

        if not self.status:
            raise ValueError("status is required for status update")

        # Normalize status to uppercase for consistency
        self.status = self.status.upper()

        # Validate status against known execution statuses
        valid_statuses = {status.value for status in ExecutionStatus}
        if self.status not in valid_statuses:
            raise ValueError(
                f"Invalid status '{self.status}'. Must be one of: {valid_statuses}"
            )

    @property
    def status_enum(self) -> ExecutionStatus:
        """Get the status as an ExecutionStatus enum."""
        return ExecutionStatus(self.status)

    @property
    def is_completed(self) -> bool:
        """Check if the execution has completed (successfully or with error)."""
        return ExecutionStatus.is_completed(self.status)

    @property
    def is_successful(self) -> bool:
        """Check if the execution completed successfully."""
        return self.status_enum == ExecutionStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """Check if the execution failed."""
        return self.status_enum == ExecutionStatus.ERROR

    def to_dict(self) -> dict[str, Any]:
        """Convert status update to dictionary for API calls."""
        result = {"execution_id": self.execution_id, "status": self.status}

        if self.organization_id:
            result["organization_id"] = self.organization_id

        if self.workflow_id:
            result["workflow_id"] = self.workflow_id

        if self.error_message:
            result["error_message"] = self.error_message

        if self.metadata:
            result["metadata"] = self.metadata

        if self.timestamp:
            result["timestamp"] = self.timestamp

        return result


@dataclass
class WorkflowConfig:
    """Type-safe workflow configuration dataclass."""

    workflow_id: str
    workflow_name: str
    workflow_type: str = "ETL"
    tools: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"

    def __post_init__(self):
        """Validate workflow configuration after initialization."""
        if not self.workflow_id:
            raise ValueError("workflow_id is required")
        if not self.workflow_name:
            raise ValueError("workflow_name is required")
        if not isinstance(self.tools, list):
            raise ValueError("tools must be a list")
        if not isinstance(self.settings, dict):
            raise ValueError("settings must be a dictionary")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")

    def get_tools_config(self) -> list[dict[str, Any]]:
        """Get tools configuration as list of dictionaries."""
        return self.tools

    def add_tool(self, tool_config: dict[str, Any]) -> None:
        """Add a tool configuration to the workflow."""
        if not isinstance(tool_config, dict):
            raise ValueError("tool_config must be a dictionary")
        if "tool_id" not in tool_config:
            raise ValueError("tool_config must contain tool_id")
        self.tools.append(tool_config)

    def get_tool_by_id(self, tool_id: str) -> dict[str, Any] | None:
        """Get a tool configuration by ID."""
        for tool in self.tools:
            if tool.get("tool_id") == tool_id:
                return tool
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert workflow config to dictionary for backward compatibility."""
        return serialize_dataclass_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowConfig":
        """Create WorkflowConfig from dictionary data."""
        return cls(
            workflow_id=data["workflow_id"],
            workflow_name=data["workflow_name"],
            workflow_type=data.get("workflow_type", "ETL"),
            tools=data.get("tools", []),
            settings=data.get("settings", {}),
            metadata=data.get("metadata", {}),
            version=data.get("version", "1.0.0"),
        )


# Additional utility functions for context conversion
def create_organization_context(
    organization_id: str,
    api_client: "InternalAPIClient",
    organization_data: dict[str, Any] | None = None,
) -> WorkerOrganizationContext:
    """Create organization context from basic parameters."""
    return WorkerOrganizationContext(
        organization_id=organization_id,
        api_client=api_client,
        organization_data=organization_data,
    )


@dataclass
class WorkflowEndpointContext:
    """Strongly-typed context for workflow endpoint configuration.

    Provides type-safe structure for workflow source and destination
    endpoint configurations with validation and utility methods.
    """

    source_endpoint: dict[str, Any] | None = None
    destination_endpoint: dict[str, Any] | None = None
    endpoints: list[dict[str, Any]] = field(default_factory=list)
    has_api_endpoints: bool = False

    def __post_init__(self):
        """Validate endpoint context after initialization."""
        # Automatically detect API endpoints if not explicitly set
        if not self.has_api_endpoints and self.endpoints:
            self.has_api_endpoints = any(
                endpoint.get("connection_type") == "API" for endpoint in self.endpoints
            )

    @property
    def has_source_endpoint(self) -> bool:
        """Check if workflow has a source endpoint."""
        return bool(self.source_endpoint)

    @property
    def has_destination_endpoint(self) -> bool:
        """Check if workflow has a destination endpoint."""
        return bool(self.destination_endpoint)

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
        return (
            self.has_api_endpoints
            or self.source_connection_type == "API"
            or self.destination_connection_type == "API"
        )

    @property
    def is_filesystem_workflow(self) -> bool:
        """Check if this is a filesystem-based workflow."""
        return (
            self.source_connection_type == "FILESYSTEM"
            or self.destination_connection_type == "FILESYSTEM"
        )

    def get_endpoint_by_type(self, endpoint_type: str) -> dict[str, Any] | None:
        """Get endpoint by type (SOURCE or DESTINATION)."""
        for endpoint in self.endpoints:
            if endpoint.get("endpoint_type") == endpoint_type:
                return endpoint
        return None


@dataclass
class WorkflowCompilationContext:
    """Strongly-typed context for workflow compilation results.

    Contains compilation status, tools configuration, and any compilation
    errors or warnings generated during workflow preparation.
    """

    workflow_id: str
    compilation_successful: bool
    tools_config: dict[str, Any] | None = None
    compilation_errors: list[str] = field(default_factory=list)
    compilation_warnings: list[str] = field(default_factory=list)
    compiled_at: str | None = None
    compilation_time: float | None = None

    def __post_init__(self):
        """Validate compilation context after initialization."""
        if not self.workflow_id:
            raise ValueError("workflow_id is required for compilation context")

    @property
    def has_errors(self) -> bool:
        """Check if compilation has errors."""
        return bool(self.compilation_errors)

    @property
    def has_warnings(self) -> bool:
        """Check if compilation has warnings."""
        return bool(self.compilation_warnings)

    @property
    def is_successful(self) -> bool:
        """Check if compilation was successful."""
        return self.compilation_successful and not self.has_errors

    def add_error(self, error_message: str) -> None:
        """Add a compilation error."""
        self.compilation_errors.append(error_message)
        self.compilation_successful = False

    def add_warning(self, warning_message: str) -> None:
        """Add a compilation warning."""
        self.compilation_warnings.append(warning_message)

    def get_error_summary(self) -> str:
        """Get a summary of all compilation errors."""
        if not self.compilation_errors:
            return "No compilation errors"
        return "; ".join(self.compilation_errors)


@dataclass
class WorkflowSourceContext:
    """Strongly-typed context for workflow source configuration.

    Manages source file access, connection details, and file listing
    operations for workflow execution.
    """

    connection_type: str
    endpoint_config: dict[str, Any]
    use_file_history: bool = True
    total_files: int = 0
    source_files: list[dict[str, Any]] = field(default_factory=list)
    file_listing_errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate source context after initialization."""
        if not self.connection_type:
            raise ValueError("connection_type is required for source context")

        if not isinstance(self.endpoint_config, dict):
            raise ValueError("endpoint_config must be a dictionary")

    @property
    def has_files(self) -> bool:
        """Check if source has files available."""
        return self.total_files > 0

    @property
    def is_api_source(self) -> bool:
        """Check if this is an API source."""
        return self.connection_type == "API"

    @property
    def is_filesystem_source(self) -> bool:
        """Check if this is a filesystem source."""
        return self.connection_type == "FILESYSTEM"

    @property
    def has_listing_errors(self) -> bool:
        """Check if file listing had errors."""
        return bool(self.file_listing_errors)

    def add_listing_error(self, error_message: str) -> None:
        """Add a file listing error."""
        self.file_listing_errors.append(error_message)

    def update_file_count(self, count: int) -> None:
        """Update the total file count."""
        self.total_files = count


@dataclass
class WorkflowDestinationContext:
    """Strongly-typed context for workflow destination configuration.

    Manages destination output configuration, connection details, and
    result delivery settings for workflow execution.
    """

    connection_type: str
    endpoint_config: dict[str, Any]
    output_format: str = "JSON"
    delivery_method: str = "PUSH"
    destination_errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate destination context after initialization."""
        if not self.connection_type:
            raise ValueError("connection_type is required for destination context")

        if not isinstance(self.endpoint_config, dict):
            raise ValueError("endpoint_config must be a dictionary")

    @property
    def is_api_destination(self) -> bool:
        """Check if this is an API destination."""
        return self.connection_type == "API"

    @property
    def is_filesystem_destination(self) -> bool:
        """Check if this is a filesystem destination."""
        return self.connection_type == "FILESYSTEM"

    @property
    def is_manual_review_destination(self) -> bool:
        """Check if this is a manual review destination."""
        return self.connection_type == "MANUALREVIEW"

    @property
    def has_errors(self) -> bool:
        """Check if destination has errors."""
        return bool(self.destination_errors)

    def add_error(self, error_message: str) -> None:
        """Add a destination error."""
        self.destination_errors.append(error_message)


@dataclass
class EnhancedWorkflowContext:
    """Enhanced workflow context that combines all workflow-related contexts.

    This provides a comprehensive, strongly-typed workflow context that includes
    execution, endpoints, compilation, source, and destination information.
    """

    # Core execution context
    execution_context: WorkflowContextData

    # Endpoint configuration context
    endpoint_context: WorkflowEndpointContext | None = None

    # Compilation context
    compilation_context: WorkflowCompilationContext | None = None

    # Source context
    source_context: WorkflowSourceContext | None = None

    # Destination context
    destination_context: WorkflowDestinationContext | None = None

    # Additional metadata
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self):
        """Validate enhanced workflow context."""
        if not self.execution_context:
            raise ValueError(
                "execution_context is required for enhanced workflow context"
            )

    @property
    def workflow_id(self) -> str:
        """Get workflow ID from execution context."""
        return self.execution_context.workflow_id

    @property
    def execution_id(self) -> str:
        """Get execution ID from execution context."""
        return self.execution_context.execution_id

    @property
    def organization_id(self) -> str:
        """Get organization ID from execution context."""
        return self.execution_context.organization_context.organization_id

    @property
    def is_api_workflow(self) -> bool:
        """Check if this is an API workflow based on all available context."""
        # Check execution context first
        if self.execution_context.is_api_workflow:
            return True

        # Check endpoint context
        if self.endpoint_context and self.endpoint_context.is_api_workflow:
            return True

        return False

    @property
    def is_compilation_successful(self) -> bool:
        """Check if workflow compilation was successful."""
        if not self.compilation_context:
            return True  # Assume success if no compilation context
        return self.compilation_context.is_successful

    @property
    def has_source_files(self) -> bool:
        """Check if workflow has source files available."""
        if not self.source_context:
            return False
        return self.source_context.has_files

    @property
    def total_files(self) -> int:
        """Get total number of files in the workflow."""
        if self.source_context:
            return self.source_context.total_files
        return self.execution_context.file_count

    def validate_for_execution(self) -> list[str]:
        """Validate the complete workflow context for execution readiness.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check compilation
        if self.compilation_context and not self.compilation_context.is_successful:
            errors.extend(self.compilation_context.compilation_errors)

        # Check source context
        if self.source_context and self.source_context.has_listing_errors:
            errors.extend(self.source_context.file_listing_errors)

        # Check destination context
        if self.destination_context and self.destination_context.has_errors:
            errors.extend(self.destination_context.destination_errors)

        # Check if API workflow has required pipeline_id
        if self.is_api_workflow:
            try:
                self.execution_context.validate_for_api_workflow()
            except ValueError as e:
                errors.append(str(e))

        return errors


def create_workflow_context_from_dict(
    context_dict: dict[str, Any],
) -> WorkflowContextData:
    """Convert dictionary-based workflow context to strongly-typed dataclass.

    Args:
        context_dict: Dictionary containing workflow context data

    Returns:
        WorkflowContextData dataclass instance
    """
    required_fields = [
        "workflow_id",
        "workflow_name",
        "workflow_type",
        "execution_id",
        "files",
    ]
    missing_fields = [field for field in required_fields if field not in context_dict]

    if missing_fields:
        raise ValueError(f"Missing required workflow context fields: {missing_fields}")

    # Create organization context if not provided
    org_context = context_dict.get("organization_context")
    if not org_context:
        org_id = context_dict.get("organization_id")
        api_client = context_dict.get("api_client")
        if org_id and api_client:
            org_context = create_organization_context(org_id, api_client)
        else:
            raise ValueError(
                "Either organization_context or both organization_id and api_client are required"
            )

    return WorkflowContextData(
        workflow_id=context_dict["workflow_id"],
        workflow_name=context_dict["workflow_name"],
        workflow_type=context_dict["workflow_type"],
        execution_id=context_dict["execution_id"],
        organization_context=org_context,
        files=context_dict["files"],
        settings=context_dict.get("settings"),
        metadata=context_dict.get("metadata"),
        is_scheduled=context_dict.get("scheduled", False),
    )
