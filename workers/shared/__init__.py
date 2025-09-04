"""Shared Worker Infrastructure

This module provides common infrastructure and utilities for lightweight Celery workers
that communicate with Django backend via internal APIs instead of direct ORM access.

Key components organized by SOLID principles:
- API communication layer (api/)
- Workflow execution components (workflow/)
- File and data processing (processing/)
- Infrastructure services (infrastructure/)
- Design patterns and utilities (patterns/)
- Core interfaces and types (core/)
- Data models, enums, and constants (data/)
"""

# Simplified imports to avoid circular dependencies during initialization
# Individual imports for key components

# Import core exceptions directly
from .core.exceptions.api_exceptions import APIClientError
from .core.exceptions.base_exceptions import WorkerBaseError
from .core.exceptions.workflow_exceptions import WorkflowExecutionError

# Import configuration and logging directly
from .infrastructure.config.worker_config import WorkerConfig
from .infrastructure.logging.logger import WorkerLogger

# Import execution context
from .workflow.execution.context import WorkerExecutionContext

# Import API client with fallback
try:
    from .api.facades.legacy_client import InternalAPIClient
except ImportError:
    # Fallback for workers that don't need the full API client
    InternalAPIClient = None

__all__ = [
    # Backward compatibility - main interfaces
    "InternalAPIClient",
    "WorkerConfig",
    "WorkerLogger",
    "WorkerExecutionContext",
    # Core interfaces and exceptions
    "APIClientInterface",
    "WorkflowExecutorInterface",
    "ConnectorInterface",
    "WorkerBaseError",
    "APIClientError",
    "WorkflowExecutionError",
    # Pattern utilities
    "RetryUtils",
    "BackoffUtils",
]

__version__ = "1.0.0"
