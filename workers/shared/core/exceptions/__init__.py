"""Centralized exception hierarchy for workers.

This module provides a unified exception hierarchy following SOLID principles,
ensuring consistent error handling across all worker components.
"""

from .api_exceptions import (
    APIClientError,
    APIRequestError,
    AuthenticationError,
    InternalAPIClientError,
)
from .base_exceptions import WorkerBaseError
from .connector_exceptions import (
    ConnectorConfigurationError,
    ConnectorConnectionError,
    ConnectorError,
)
from .workflow_exceptions import (
    WorkflowConfigurationError,
    WorkflowExecutionError,
    WorkflowValidationError,
)

__all__ = [
    # Base exception
    "WorkerBaseError",
    # API exceptions
    "APIClientError",
    "APIRequestError",
    "AuthenticationError",
    "InternalAPIClientError",
    # Connector exceptions
    "ConnectorError",
    "ConnectorConfigurationError",
    "ConnectorConnectionError",
    # Workflow exceptions
    "WorkflowExecutionError",
    "WorkflowConfigurationError",
    "WorkflowValidationError",
]
