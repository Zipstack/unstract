"""Connector related exceptions.

These exceptions handle connector-specific error scenarios following
the Single Responsibility Principle.
"""

from .base_exceptions import WorkerBaseError


class ConnectorError(WorkerBaseError):
    """Base exception for connector errors."""

    def __init__(
        self, message: str, connector_type: str = None, connector_id: str = None, **kwargs
    ):
        super().__init__(message, **kwargs)
        self.connector_type = connector_type
        self.connector_id = connector_id


class ConnectorConfigurationError(ConnectorError):
    """Raised when connector configuration is invalid."""

    pass


class ConnectorConnectionError(ConnectorError):
    """Raised when connector fails to establish connection."""

    pass


class ConnectorAuthenticationError(ConnectorError):
    """Raised when connector authentication fails."""

    pass


class ConnectorPermissionError(ConnectorError):
    """Raised when connector lacks required permissions."""

    pass
