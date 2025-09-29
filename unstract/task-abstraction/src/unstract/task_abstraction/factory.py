"""Backend factory for creating task backend instances."""

import logging
import os
from typing import Dict, Type, Union, Optional
from .base import TaskBackend
from .models import BackendConfig
from .config import load_config_from_file, load_config_from_env

logger = logging.getLogger(__name__)


# Registry of available backend implementations
BACKEND_REGISTRY: Dict[str, Type[TaskBackend]] = {}


def register_backend(backend_type: str, backend_class: Type[TaskBackend]) -> None:
    """Register a backend implementation.

    Args:
        backend_type: Backend type identifier (celery, hatchet, temporal)
        backend_class: Backend implementation class
    """
    BACKEND_REGISTRY[backend_type] = backend_class


def get_available_backends() -> list[str]:
    """Get list of available backend types.

    Returns:
        List of registered backend type names
    """
    return list(BACKEND_REGISTRY.keys())


def create_backend(backend_type: str, config: Optional[BackendConfig] = None) -> TaskBackend:
    """Create a backend instance of the specified type.

    Args:
        backend_type: Backend type (celery, hatchet, temporal)
        config: Optional backend configuration

    Returns:
        TaskBackend instance

    Raises:
        ValueError: If backend type is not supported
        ImportError: If backend dependencies are not installed

    Note:
        Resilience features (retries, DLQ, persistence) should be configured
        in the backend's native configuration.

    Example:
        backend = create_backend("celery")
        backend = create_backend("hatchet", config=hatchet_config)
    """
    if backend_type not in BACKEND_REGISTRY:
        available = ", ".join(get_available_backends())
        logger.error(f"Unsupported backend type '{backend_type}'. Available: {available}")
        raise ValueError(
            f"Backend type '{backend_type}' not supported. "
            f"Available backends: {available}"
        )

    backend_class = BACKEND_REGISTRY[backend_type]
    logger.info(f"Creating {backend_type} backend instance")

    try:
        return backend_class(config)
    except ImportError as e:
        logger.error(f"Failed to create {backend_type} backend: {e}")
        raise ImportError(
            f"Failed to create {backend_type} backend: {e}. "
            f"Install required dependencies for {backend_type} backend."
        ) from e


def get_backend(config: Optional[Union[BackendConfig, str]] = None) -> TaskBackend:
    """Get a task backend instance with automatic configuration loading.

    Auto-detects backend type from TASK_BACKEND_TYPE environment variable.
    This provides true abstraction - client code doesn't need to know which backend is configured.

    Args:
        config: Optional backend configuration. Can be:
                - BackendConfig instance (must specify backend_type)
                - Path to YAML config file (str)
                - None (auto-detect from TASK_BACKEND_TYPE environment variable)

    Returns:
        TaskBackend instance ready for use

    Example:
        # Auto-detect from environment (TASK_BACKEND_TYPE=celery)
        backend = get_backend()  # Pure abstraction!

        # Use config file
        backend = get_backend(config="config.yaml")

        # Use explicit config
        config = BackendConfig(backend_type="celery", ...)
        backend = get_backend(config=config)
    """
    # Load configuration if needed
    if isinstance(config, str):
        # Config is a file path
        backend_config = load_config_from_file(config)
        backend_type = backend_config.backend_type
    elif isinstance(config, BackendConfig):
        # Config is already a BackendConfig
        backend_config = config
        backend_type = backend_config.backend_type
    else:
        # No config provided - auto-detect backend type from environment
        backend_type = os.getenv("TASK_BACKEND_TYPE")
        if not backend_type:
            logger.error("TASK_BACKEND_TYPE environment variable not set")
            raise ValueError(
                "TASK_BACKEND_TYPE environment variable must be set. "
                "Example: TASK_BACKEND_TYPE=celery"
            )
        logger.info(f"Auto-detected backend type from environment: {backend_type}")

        # Load configuration from environment
        backend_config = load_config_from_env(backend_type)

    return create_backend(backend_type, backend_config)


# Auto-register available backends
def _register_available_backends():
    """Register all available backend implementations."""
    # Try to register Celery backend
    try:
        from .backends.celery import CeleryBackend
        register_backend("celery", CeleryBackend)
        logger.debug("Registered Celery backend")
    except ImportError:
        logger.debug("Celery backend not available")

    # Try to register Hatchet backend
    try:
        from .backends.hatchet import HatchetBackend
        register_backend("hatchet", HatchetBackend)
        logger.debug("Registered Hatchet backend")
    except ImportError:
        logger.debug("Hatchet backend not available")

    # Try to register Temporal backend
    try:
        from .backends.temporal import TemporalBackend
        register_backend("temporal", TemporalBackend)
        logger.debug("Registered Temporal backend")
    except ImportError:
        logger.debug("Temporal backend not available")


# Register backends on module import
_register_available_backends()