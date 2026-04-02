"""Core interfaces and abstractions for the workers shared library.

This package provides the foundational interfaces, exceptions, and type definitions
that serve as contracts for the entire workers system.
"""

from .exceptions import *  # noqa: F403
from .interfaces import *  # noqa: F403

__all__ = [
    # Interfaces
    "APIClientInterface",
    "CacheInterface",
    "ConnectorInterface",
    "WorkflowExecutorInterface",
    # Exceptions
    "WorkerBaseError",
    "APIClientError",
    "WorkflowExecutionError",
    "ConnectorError",
    # Types
    "APIResponse",
    "WorkflowContext",
]
