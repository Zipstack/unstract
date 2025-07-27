"""Worker-Specific Exceptions

This module provides worker-specific exceptions that mirror the backend endpoint exceptions
for consistent error handling between backend API endpoints and worker operations.

These exceptions are designed to be raised by workers and handled by the task execution
system for proper error reporting and debugging.
"""


class WorkerError(Exception):
    """Base exception for all worker-related errors."""

    def __init__(self, message: str, details: str = None):
        self.message = message
        self.details = details
        super().__init__(message)

    def __str__(self):
        if self.details:
            return f"{self.message}. Details: {self.details}"
        return self.message


class ConnectorError(WorkerError):
    """Base exception for connector-related errors."""

    pass


class ConnectorNotAvailableError(ConnectorError):
    """Raised when connector packages/modules are not available in worker environment."""

    def __init__(self, connector_type: str = None, import_error: str = None):
        if connector_type:
            message = f"Connector type '{connector_type}' is not available in worker environment"
        else:
            message = "Connector packages are not available in worker environment"

        details = f"Import error: {import_error}" if import_error else None
        super().__init__(message, details)


class InvalidSourceConnectionType(ConnectorError):
    """Raised when the provided source connection type is invalid."""

    def __init__(self, connection_type: str = None, valid_types: list = None):
        if connection_type:
            message = f"Invalid source connection type: '{connection_type}'"
            if valid_types:
                message += f". Valid types: {valid_types}"
        else:
            message = "The provided source connection type is invalid"
        super().__init__(message)


class MissingSourceConnectionType(ConnectorError):
    """Raised when the source connection type is missing."""

    def __init__(self):
        super().__init__(
            "The source connection type is missing from source configuration"
        )


class SourceConnectorNotConfigured(ConnectorError):
    """Raised when the source connector is not properly configured."""

    def __init__(self, connector_id: str = None):
        if connector_id:
            message = f"Source connector '{connector_id}' is not properly configured"
        else:
            message = "The source connector is not configured"
        super().__init__(message)


class ConnectorConnectionError(ConnectorError):
    """Raised when unable to connect to the source connector."""

    def __init__(self, connector_id: str, connection_details: str = None):
        message = f"Failed to connect to source connector '{connector_id}'"
        super().__init__(message, connection_details)


class InvalidInputDirectory(ConnectorError):
    """Raised when the provided directory path is not valid or accessible."""

    def __init__(self, directory: str = None, reason: str = None):
        if directory:
            message = f"Invalid input directory: '{directory}'"
        else:
            message = "The provided path is not a valid directory"
        super().__init__(message, reason)


class SourceFileListingError(ConnectorError):
    """Raised when file listing from source connector fails."""

    def __init__(self, connector_id: str, error_details: str = None):
        message = f"Failed to list files from source connector '{connector_id}'"
        super().__init__(message, error_details)


class UnsupportedConnectorType(ConnectorError):
    """Raised when the connector type is not supported by the worker."""

    def __init__(self, connector_id: str, available_connectors: list = None):
        message = f"Connector '{connector_id}' is not supported"
        details = None
        if available_connectors:
            details = f"Available connectors: {available_connectors}"
        super().__init__(message, details)


class ConnectorConfigurationError(ConnectorError):
    """Raised when connector configuration is invalid or incomplete."""

    def __init__(
        self, connector_id: str, missing_fields: list = None, invalid_values: dict = None
    ):
        message = f"Invalid configuration for connector '{connector_id}'"

        details_parts = []
        if missing_fields:
            details_parts.append(f"Missing required fields: {missing_fields}")
        if invalid_values:
            details_parts.append(f"Invalid values: {invalid_values}")

        details = "; ".join(details_parts) if details_parts else None
        super().__init__(message, details)


class WorkflowSourceError(WorkerError):
    """Base exception for workflow source-related errors."""

    pass


class WorkflowNotFound(WorkflowSourceError):
    """Raised when workflow is not found or not accessible."""

    def __init__(self, workflow_id: str, organization_id: str = None):
        message = f"Workflow '{workflow_id}' not found"
        details = f"Organization: {organization_id}" if organization_id else None
        super().__init__(message, details)


class SourceConfigurationNotFound(WorkflowSourceError):
    """Raised when workflow source configuration is missing."""

    def __init__(self, workflow_id: str):
        message = f"Source configuration not found for workflow '{workflow_id}'"
        super().__init__(message)


class InvalidSourceConfiguration(WorkflowSourceError):
    """Raised when workflow source configuration is invalid."""

    def __init__(self, workflow_id: str, validation_errors: list = None):
        message = f"Invalid source configuration for workflow '{workflow_id}'"
        details = f"Validation errors: {validation_errors}" if validation_errors else None
        super().__init__(message, details)


class OrganizationContextError(WorkerError):
    """Raised when organization context is missing or invalid."""

    def __init__(self, organization_id: str = None):
        if organization_id:
            message = f"Invalid organization context: '{organization_id}'"
        else:
            message = "Organization context is missing or not accessible"
        super().__init__(message)


# Exception mapping for converting backend exceptions to worker exceptions
BACKEND_TO_WORKER_EXCEPTION_MAP = {
    "InvalidInputDirectory": InvalidInputDirectory,
    "InvalidSourceConnectionType": InvalidSourceConnectionType,
    "MissingSourceConnectionType": MissingSourceConnectionType,
    "SourceConnectorNotConfigured": SourceConnectorNotConfigured,
    "OrganizationIdNotFound": OrganizationContextError,
}


def map_backend_exception(backend_exception_name: str, *args, **kwargs) -> WorkerError:
    """Map a backend exception name to the corresponding worker exception.

    Args:
        backend_exception_name: Name of the backend exception class
        *args, **kwargs: Arguments to pass to the worker exception constructor

    Returns:
        WorkerError instance
    """
    worker_exception_class = BACKEND_TO_WORKER_EXCEPTION_MAP.get(
        backend_exception_name, WorkerError
    )
    return worker_exception_class(*args, **kwargs)
