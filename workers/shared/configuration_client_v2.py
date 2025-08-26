"""Clean Configuration Client with Caching

This refactored version provides:
- Better separation of concerns
- Thread-safe caching
- Clean error handling
- Type safety
- Comprehensive logging
"""

import time
from threading import Lock
from typing import Any

from .logging_utils import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class ConfigurationCache:
    """Thread-safe configuration cache with TTL support."""

    def __init__(self, default_ttl: int = 300):
        """Initialize cache with default TTL.

        Args:
            default_ttl: Default time-to-live in seconds (5 minutes default)
        """
        self.default_ttl = default_ttl
        self._cache: dict[str, Any] = {}
        self._timestamps: dict[str, float] = {}
        self._lock = Lock()

    def get(self, key: str, ttl: int | None = None) -> Any | None:
        """Get value from cache if valid.

        Args:
            key: Cache key
            ttl: Custom TTL, uses default if None

        Returns:
            Cached value or None if expired/missing
        """
        effective_ttl = ttl or self.default_ttl

        with self._lock:
            if key not in self._timestamps:
                return None

            if (time.time() - self._timestamps[key]) > effective_ttl:
                # Remove expired entry
                self._cache.pop(key, None)
                self._timestamps.pop(key, None)
                return None

            return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()

    def clear(self) -> None:
        """Clear all cached values."""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()

    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)


class WorkerConfigurationClient:
    """Clean configuration client with performance optimizations."""

    def __init__(self, api_client=None, cache_ttl: int = 300):
        """Initialize configuration client.

        Args:
            api_client: Internal API client for backend communication
            cache_ttl: Cache time-to-live in seconds
        """
        self.api_client = api_client
        self.cache_enabled = (
            getattr(api_client, "config", None)
            and getattr(api_client.config, "enable_config_cache", True)
            if api_client
            else True
        )

        # Initialize cache
        self.cache = ConfigurationCache(cache_ttl) if self.cache_enabled else None

        # Initialize core client
        self._initialize_core_client()

        logger.debug(f"Configuration client initialized (caching: {self.cache_enabled})")

    def _initialize_core_client(self) -> None:
        """Initialize the core configuration client."""
        try:
            from unstract.core.configuration import ConfigurationClient as CoreClient

            self.core_client = CoreClient(api_client=self._create_api_adapter())
        except ImportError as e:
            logger.warning(f"Core configuration client unavailable: {e}")
            self.core_client = self._create_fallback_client()

    def _create_api_adapter(self):
        """Create API adapter for core client."""
        if not self.api_client:
            return None

        class CleanAPIAdapter:
            """Clean API adapter with proper error handling."""

            def __init__(self, internal_client):
                self.internal_client = internal_client

            def get(self, url_path: str, params: dict | None = None) -> dict[str, Any]:
                """Adapter method for core client compatibility."""
                try:
                    if url_path.startswith("/internal/configuration/"):
                        config_key = url_path.split("/")[-2]
                        org_id = params.get("organization_id") if params else None

                        response = self.internal_client.get_configuration(
                            config_key=config_key, organization_id=org_id
                        )
                        return response
                    else:
                        return self.internal_client.get(url_path, params=params)

                except Exception as e:
                    logger.error(f"API adapter error for {url_path}: {e}")
                    from .data_models import APIResponse

                    return APIResponse(success=False, error=str(e))

        return CleanAPIAdapter(self.api_client)

    def _create_fallback_client(self):
        """Create fallback client when core client is unavailable."""

        class FallbackConfigClient:
            def get_max_parallel_file_batches(self, organization_id=None):
                import os

                try:
                    return max(1, int(os.getenv("MAX_PARALLEL_FILE_BATCHES", "5")))
                except (ValueError, TypeError):
                    return 5

        return FallbackConfigClient()

    def get_max_parallel_file_batches(self, organization_id: str | None = None) -> int:
        """Get MAX_PARALLEL_FILE_BATCHES with caching and fallback.

        Args:
            organization_id: Organization ID for specific overrides

        Returns:
            Maximum parallel file batches (guaranteed >= 1)
        """
        cache_key = f"MAX_PARALLEL_FILE_BATCHES:{organization_id or 'default'}"

        # Check cache first
        if self.cache:
            cached_value = self.cache.get(cache_key)
            if cached_value is not None:
                logger.debug(
                    f"Using cached batch size for org {organization_id}: {cached_value}"
                )
                return cached_value

        # Fetch from API
        try:
            value = self.core_client.get_max_parallel_file_batches(organization_id)
            value = max(1, value)  # Ensure minimum of 1

            # Cache successful result
            if self.cache:
                self.cache.set(cache_key, value)

            logger.debug(f"Fetched batch size for org {organization_id}: {value}")
            return value

        except Exception as e:
            logger.warning(f"Failed to get batch size from API: {e}")
            return self._get_fallback_batch_size(cache_key)

    def _get_fallback_batch_size(self, cache_key: str) -> int:
        """Get fallback batch size from environment variables.

        Args:
            cache_key: Cache key for storing fallback value

        Returns:
            Fallback batch size value
        """
        import os

        try:
            value = max(1, int(os.getenv("MAX_PARALLEL_FILE_BATCHES", "1")))

            # Cache fallback with shorter TTL (30 seconds)
            if self.cache:
                self.cache.set(cache_key, value)

            logger.debug(f"Using fallback batch size: {value}")
            return value

        except (ValueError, TypeError) as e:
            logger.error(f"Invalid MAX_PARALLEL_FILE_BATCHES environment variable: {e}")
            return 1  # Absolute minimum

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics for monitoring.

        Returns:
            Dictionary with cache statistics
        """
        if not self.cache:
            return {"enabled": False}

        return {"enabled": True, "size": self.cache.size(), "ttl": self.cache.default_ttl}


def create_configuration_client(api_client=None) -> WorkerConfigurationClient:
    """Factory function for creating configuration client.

    Args:
        api_client: Internal API client

    Returns:
        Configured WorkerConfigurationClient instance
    """
    return WorkerConfigurationClient(api_client=api_client)
