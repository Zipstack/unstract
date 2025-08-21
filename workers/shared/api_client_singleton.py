"""Global API Client Singleton Manager

Provides a singleton pattern for API clients to reduce repeated initialization
and eliminate excessive logging noise from health checks.
"""

import threading

from .api_client_facade import InternalAPIClient
from .config import WorkerConfig
from .logging_utils import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class APIClientSingleton:
    """Thread-safe singleton manager for API clients."""

    _instance = None
    _lock = threading.Lock()
    _clients: dict[str, InternalAPIClient] = {}
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def get_client(self, config: WorkerConfig | None = None) -> InternalAPIClient:
        """Get or create an API client for the given configuration.

        Args:
            config: Worker configuration. Uses default if None.

        Returns:
            InternalAPIClient instance (cached)
        """
        if config is None:
            config = WorkerConfig()

        # Create a cache key based on API base URL and key
        cache_key = f"{config.internal_api_base_url}:{config.internal_api_key[:8] if config.internal_api_key else 'none'}"

        if cache_key not in self._clients:
            with self._lock:
                # Double-check pattern
                if cache_key not in self._clients:
                    if not self._initialized:
                        logger.debug("Initializing global API client singleton")
                        self._initialized = True
                    else:
                        logger.debug(f"Creating new API client for config: {cache_key}")

                    self._clients[cache_key] = InternalAPIClient(config)

        return self._clients[cache_key]

    def clear_cache(self):
        """Clear all cached clients (useful for testing)."""
        with self._lock:
            self._clients.clear()
            self._initialized = False
            logger.debug("Cleared API client cache")


# Global singleton instance
_api_client_singleton = APIClientSingleton()


def get_singleton_api_client(config: WorkerConfig | None = None) -> InternalAPIClient:
    """Get a singleton API client instance.

    This function provides a convenient way to get a cached API client
    that reduces initialization overhead and logging noise.

    Args:
        config: Worker configuration. Uses default if None.

    Returns:
        InternalAPIClient instance (cached)
    """
    return _api_client_singleton.get_client(config)


def clear_api_client_cache():
    """Clear the API client cache (useful for testing)."""
    _api_client_singleton.clear_cache()
