"""Core interfaces and protocols for the workers system.

These interfaces define contracts that must be followed by all implementations,
adhering to the Interface Segregation Principle by providing focused,
role-specific interfaces.
"""

from .api_interfaces import APIClientInterface, CacheInterface
from .connector_interfaces import (
    ConnectorInterface,
    DestinationConnectorInterface,
    SourceConnectorInterface,
)
from .workflow_interfaces import WorkflowExecutorInterface, WorkflowValidatorInterface

__all__ = [
    # API interfaces
    "APIClientInterface",
    "CacheInterface",
    # Connector interfaces
    "ConnectorInterface",
    "SourceConnectorInterface",
    "DestinationConnectorInterface",
    # Workflow interfaces
    "WorkflowExecutorInterface",
    "WorkflowValidatorInterface",
]
