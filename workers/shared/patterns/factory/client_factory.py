"""API Client Factory for Performance-Optimized Client Creation

This module provides a clean factory pattern for creating API clients with
performance optimizations while maintaining readability and testability.
"""

from threading import Lock
from typing import TypeVar

from ...clients.base_client import BaseAPIClient
from ...clients.execution_client import ExecutionAPIClient
from ...clients.file_client import FileAPIClient
from ...clients.organization_client import OrganizationAPIClient
from ...clients.tool_client import ToolAPIClient
from ...clients.webhook_client import WebhookAPIClient
from ...infrastructure.config.worker_config import WorkerConfig
from ...infrastructure.logging import WorkerLogger

logger = WorkerLogger.get_logger(__name__)

ClientType = TypeVar("ClientType", bound=BaseAPIClient)


class ClientFactory:
    """Thread-safe factory for creating API clients with performance optimizations."""

    # Class-level shared resources
    _shared_base_client: BaseAPIClient | None = None
    _client_lock = Lock()
    _initialization_count = 0

    # Client type registry
    CLIENT_TYPES = {
        "execution": ExecutionAPIClient,
        "file": FileAPIClient,
        "webhook": WebhookAPIClient,
        "organization": OrganizationAPIClient,
        "tool": ToolAPIClient,
    }

    def __init__(self, config: WorkerConfig):
        """Initialize factory with worker configuration.

        Args:
            config: Worker configuration instance
        """
        self.config = config

    def create_base_client(self) -> BaseAPIClient:
        """Create or return shared base client using singleton pattern.

        Returns:
            BaseAPIClient instance (shared if singleton enabled)
        """
        if not self.config.enable_api_client_singleton:
            return self._create_new_base_client()

        with ClientFactory._client_lock:
            if ClientFactory._shared_base_client is None:
                if self.config.debug_api_client_init:
                    logger.info(
                        "Creating shared BaseAPIClient instance (singleton pattern)"
                    )
                ClientFactory._shared_base_client = self._create_new_base_client()

            ClientFactory._initialization_count += 1

            if self.config.debug_api_client_init:
                logger.info(
                    f"Reusing shared BaseAPIClient instance (#{ClientFactory._initialization_count})"
                )

            return ClientFactory._shared_base_client

    def _create_new_base_client(self) -> BaseAPIClient:
        """Create a new BaseAPIClient instance.

        Returns:
            New BaseAPIClient instance
        """
        return BaseAPIClient(self.config)

    def create_specialized_client(
        self, client_type: str, base_client: BaseAPIClient
    ) -> BaseAPIClient:
        """Create a specialized client with proper fallback handling.

        Args:
            client_type: Type of client to create ('execution', 'file', etc.)
            base_client: Base client to potentially share configuration

        Returns:
            Specialized client instance

        Raises:
            ValueError: If client_type is not supported
        """
        if client_type not in self.CLIENT_TYPES:
            raise ValueError(f"Unknown client type: {client_type}")

        client_class = self.CLIENT_TYPES[client_type]

        # Try to use from_base_client if available, otherwise fallback to config
        if hasattr(client_class, "from_base_client") and callable(
            client_class.from_base_client
        ):
            try:
                return client_class.from_base_client(base_client)
            except Exception as e:
                logger.warning(
                    f"Failed to create {client_type} client from base client: {e}"
                )
                logger.info(
                    f"Falling back to config-based initialization for {client_type} client"
                )

        return client_class(self.config)

    def create_all_clients(self) -> dict[str, BaseAPIClient]:
        """Create all specialized clients using the factory pattern.

        Returns:
            Dictionary mapping client names to client instances
        """
        base_client = self.create_base_client()

        clients = {"base": base_client}

        for client_type in self.CLIENT_TYPES.keys():
            try:
                clients[client_type] = self.create_specialized_client(
                    client_type, base_client
                )
            except Exception as e:
                logger.error(f"Failed to create {client_type} client: {e}")
                # Continue with other clients even if one fails
                continue

        return clients

    @classmethod
    def reset_shared_state(cls) -> None:
        """Reset shared state for testing purposes.

        Warning:
            This should only be used in tests or during graceful shutdown.
        """
        with cls._client_lock:
            if cls._shared_base_client:
                try:
                    cls._shared_base_client.close()
                except Exception as e:
                    logger.warning(f"Error closing shared base client: {e}")

            cls._shared_base_client = None
            cls._initialization_count = 0
            logger.debug("Client factory shared state reset")


class CachingConfigurationMixin:
    """Mixin for adding caching functionality to configuration clients."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache: dict[str, any] = {}
        self._cache_timestamps: dict[str, float] = {}
        self._cache_lock = Lock()

    def _get_cache_key(self, key: str, org_id: str | None = None) -> str:
        """Generate cache key for configuration values."""
        return f"{key}:{org_id or 'default'}"

    def _is_cache_valid(self, cache_key: str, ttl: int = 300) -> bool:
        """Check if cached value is still valid."""
        import time

        if cache_key not in self._cache_timestamps:
            return False

        return (time.time() - self._cache_timestamps[cache_key]) < ttl

    def _get_from_cache(self, cache_key: str) -> any | None:
        """Thread-safe cache retrieval."""
        with self._cache_lock:
            return self._cache.get(cache_key)

    def _set_cache(self, cache_key: str, value: any) -> None:
        """Thread-safe cache storage."""
        import time

        with self._cache_lock:
            self._cache[cache_key] = value
            self._cache_timestamps[cache_key] = time.time()

    def _clear_cache(self) -> None:
        """Clear all cached values."""
        with self._cache_lock:
            self._cache.clear()
            self._cache_timestamps.clear()
