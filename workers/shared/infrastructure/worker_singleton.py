"""Worker Infrastructure with Lock-Free Factory Pattern

This module provides a lock-free factory pattern for managing worker-level infrastructure
components. Expensive resources like configuration and connection pools are shared,
but API clients are created per-task to ensure organization isolation and eliminate
threading issues.

Architecture:
- WorkerInfrastructure: Manages shared expensive resources (config, connection pools)
- API Client Factory: Creates isolated API clients per organization per task
- No locks: Eliminates deadlock risks and performance bottlenecks
- Organization isolation: Complete separation of API contexts between tasks
"""

import logging
from typing import Optional

from shared.api.internal_client import InternalAPIClient
from shared.infrastructure.caching import WorkerCacheManager
from shared.infrastructure.config import WorkerConfig

logger = logging.getLogger(__name__)


class WorkerInfrastructure:
    """Simple factory for worker-level infrastructure components.

    This class manages shared expensive resources (configuration, connection pools)
    while providing a factory method for creating isolated API clients per task.
    Uses Python's GIL for natural thread safety - simple and efficient.
    """

    _instance: Optional["WorkerInfrastructure"] = None
    _initialized: bool = False

    def __new__(cls) -> "WorkerInfrastructure":
        """GIL-safe singleton instantiation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize worker infrastructure if not already done."""
        # Simple idempotent initialization - GIL provides safety
        if WorkerInfrastructure._initialized:
            return

        logger.info("Initializing WorkerInfrastructure factory (GIL-safe)...")

        # Initialize configuration (shared across all tasks)
        self.config = WorkerConfig()

        # Initialize cache manager (shared across all tasks)
        self._initialize_cache_manager()

        # Mark as initialized (atomic assignment)
        WorkerInfrastructure._initialized = True

        logger.info(
            f"WorkerInfrastructure factory initialized successfully: "
            f"Config={type(self.config).__name__}, "
            f"Cache={type(self.cache_manager).__name__}"
        )

    def _initialize_cache_manager(self) -> None:
        """Initialize the worker cache manager for shared caching across tasks."""
        try:
            self.cache_manager = WorkerCacheManager(self.config)
            logger.debug("WorkerCacheManager initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize WorkerCacheManager: {e}")
            # Set to None so tasks can handle gracefully
            self.cache_manager = None

    def create_api_client(self, organization_id: str) -> InternalAPIClient:
        """Create a new API client instance for a specific organization.

        This factory method creates isolated API client instances per task,
        ensuring complete organization separation and eliminating threading issues.
        The client reuses the shared configuration but maintains its own state.

        Args:
            organization_id: The organization ID to set as context for this client

        Returns:
            A new InternalAPIClient instance configured for the specified organization

        Raises:
            RuntimeError: If worker infrastructure is not initialized
        """
        if not WorkerInfrastructure._initialized:
            raise RuntimeError("Worker infrastructure not initialized")

        try:
            # Create new API client instance for this task/organization
            api_client = InternalAPIClient(self.config)
            api_client.set_organization_context(organization_id)

            logger.debug(f"Created new API client for organization: {organization_id}")
            return api_client

        except Exception as e:
            logger.error(f"Failed to create API client for org {organization_id}: {e}")
            raise RuntimeError(f"API client creation failed: {e}") from e

    @classmethod
    def get_instance(cls) -> "WorkerInfrastructure":
        """Get the singleton instance of WorkerInfrastructure.

        Returns:
            The singleton WorkerInfrastructure instance
        """
        if cls._instance is None:
            cls()  # This will create and initialize the instance
        return cls._instance

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if the worker infrastructure has been initialized.

        Returns:
            True if infrastructure is ready, False otherwise
        """
        return cls._initialized and cls._instance is not None

    def get_cache_manager(self) -> WorkerCacheManager | None:
        """Get the shared cache manager instance.

        Returns:
            The shared WorkerCacheManager instance, or None if not available
        """
        return getattr(self, "cache_manager", None)

    def get_config(self) -> WorkerConfig:
        """Get the worker configuration.

        Returns:
            The WorkerConfig instance
        """
        return self.config

    def health_check(self) -> dict[str, bool]:
        """Perform health check on infrastructure components.

        Returns:
            Dictionary with health status of each component
        """
        health = {
            "infrastructure_initialized": self._initialized,
            "config_available": hasattr(self, "config") and self.config is not None,
            "cache_manager_available": hasattr(self, "cache_manager")
            and self.cache_manager is not None,
            "api_client_factory_available": True,  # Factory is always available if initialized
        }

        # Check cache manager health if available
        if health["cache_manager_available"]:
            health["cache_manager_redis_available"] = self.cache_manager.is_available

        return health


# Global convenience functions for easy access to shared infrastructure
# These functions provide a clean API for tasks to access shared resources


def get_worker_infrastructure() -> WorkerInfrastructure:
    """Get the worker infrastructure singleton instance.

    Returns:
        The WorkerInfrastructure singleton instance
    """
    return WorkerInfrastructure.get_instance()


def create_api_client(organization_id: str) -> InternalAPIClient:
    """Create a new API client instance for a specific organization.

    This function provides a lock-free factory for creating isolated API client
    instances per task. Each client is bound to a specific organization and
    maintains its own state, eliminating threading issues and organization conflicts.

    Args:
        organization_id: The organization ID to set as context for this client

    Returns:
        A new InternalAPIClient instance configured for the specified organization

    Raises:
        RuntimeError: If worker infrastructure is not initialized
    """
    infrastructure = get_worker_infrastructure()
    return infrastructure.create_api_client(organization_id)


def get_cache_manager() -> WorkerCacheManager | None:
    """Get the shared cache manager instance.

    This function provides convenient access to the shared WorkerCacheManager
    that is reused across all tasks within the worker process.

    Returns:
        The shared WorkerCacheManager instance, or None if not available
    """
    infrastructure = get_worker_infrastructure()
    return infrastructure.get_cache_manager()


def get_worker_config() -> WorkerConfig:
    """Get the worker configuration.

    Returns:
        The WorkerConfig instance
    """
    infrastructure = get_worker_infrastructure()
    return infrastructure.get_config()


def initialize_worker_infrastructure() -> WorkerInfrastructure:
    """Explicitly initialize worker infrastructure.

    This function should be called during worker startup to ensure
    all infrastructure components are ready before task execution begins.

    Returns:
        The initialized WorkerInfrastructure instance
    """
    logger.info("Explicitly initializing worker infrastructure...")
    infrastructure = WorkerInfrastructure.get_instance()

    # Perform health check to ensure everything is working
    health = infrastructure.health_check()
    logger.info(f"Worker infrastructure health check: {health}")

    if not health["infrastructure_initialized"] or not health["config_available"]:
        raise RuntimeError(f"Worker infrastructure initialization failed: {health}")

    logger.info("Worker infrastructure initialization completed successfully")
    return infrastructure


def worker_infrastructure_health_check() -> dict[str, bool]:
    """Get health status of worker infrastructure components.

    Returns:
        Dictionary with health status of each component
    """
    if not WorkerInfrastructure.is_initialized():
        return {"infrastructure_initialized": False}

    infrastructure = get_worker_infrastructure()
    return infrastructure.health_check()
