"""Shared Worker Infrastructure

This module provides common infrastructure and utilities for lightweight Celery workers
that communicate with Django backend via internal APIs instead of direct ORM access.

Key components:
- API client with authentication
- Retry logic and circuit breakers
- Logging and monitoring utilities
- Configuration management
- Health check endpoints
"""

from .api_client import InternalAPIClient
from .config import WorkerConfig
from .health import HealthChecker, HealthServer
from .logging_utils import WorkerLogger
from .retry_utils import CircuitBreaker, RetryHandler

__all__ = [
    "InternalAPIClient",
    "WorkerConfig",
    "WorkerLogger",
    "RetryHandler",
    "CircuitBreaker",
    "HealthChecker",
    "HealthServer",
]

__version__ = "1.0.0"
