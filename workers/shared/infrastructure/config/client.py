"""Configuration Client for Workers

This module provides access to organization-specific configurations from the backend's
configuration system without requiring Django database access.

This integrates the unstract.core.configuration module with the worker's API client
to provide seamless access to organization-level configuration overrides.
"""

from typing import Any

from shared.api import InternalAPIClient

from unstract.core.configuration import (
    ConfigurationClient as CoreConfigurationClient,
)

from ..logging import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class WorkerConfigurationClient:
    """Worker-specific configuration client wrapper.

    This extends the core configuration client with worker-specific functionality
    and integrates with the worker's internal API client.
    """

    def __init__(self, api_client: InternalAPIClient | None = None):
        """Initialize worker configuration client.

        Args:
            api_client: Internal API client for backend communication
        """
        self.api_client = api_client
        self.core_client = CoreConfigurationClient(api_client=self._create_api_adapter())

        # Configuration caching for performance optimization
        self._config_cache = {}
        self._cache_timestamps = {}
        self._cache_ttl = (
            getattr(self.api_client.config, "config_cache_ttl", 300)
            if api_client
            else 300
        )  # 5 minutes default

    def _create_api_adapter(self):
        """Create an adapter for the core configuration client to use our API client.

        The core configuration client expects a simple API client interface,
        so we create an adapter that wraps our InternalAPIClient.
        """
        if not self.api_client:
            return None

        class APIAdapter:
            def __init__(self, internal_client: InternalAPIClient):
                self.internal_client = internal_client

            def get(self, url_path: str, params: dict = None):
                """Adapter method to match core client expectations."""
                try:
                    # The core client expects URLs like "/internal/configuration/{key}/"
                    # Our internal client uses the configuration endpoints
                    if url_path.startswith("/internal/configuration/"):
                        config_key = url_path.split("/")[-2]  # Extract key from URL
                        organization_id = (
                            params.get("organization_id") if params else None
                        )

                        # Call our configuration endpoint
                        response = self.internal_client.get_configuration(
                            config_key=config_key, organization_id=organization_id
                        )

                        return response
                    else:
                        # Fallback for other URLs
                        return self.internal_client.get(url_path, params=params)

                except Exception as e:
                    logger.warning(f"Configuration API adapter error: {e}")
                    # Return a failed response object
                    from .data.models import APIResponse

                    return APIResponse(success=False, error=str(e))

        return APIAdapter(self.api_client)

    def _get_cache_key(self, config_key: str, organization_id: str | None = None) -> str:
        """Generate cache key for configuration values."""
        return f"{config_key}:{organization_id or 'default'}"

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached value is still valid."""
        if cache_key not in self._cache_timestamps:
            return False

        # Check if caching is enabled
        if (
            hasattr(self.api_client, "config")
            and hasattr(self.api_client.config, "enable_config_cache")
            and not self.api_client.config.enable_config_cache
        ):
            return False

        import time

        return (time.time() - self._cache_timestamps[cache_key]) < self._cache_ttl

    def _set_cache(self, cache_key: str, value: Any) -> None:
        """Store value in cache with timestamp."""
        import time

        self._config_cache[cache_key] = value
        self._cache_timestamps[cache_key] = time.time()

    def get_max_parallel_file_batches(self, organization_id: str | None = None) -> int:
        """Get MAX_PARALLEL_FILE_BATCHES configuration for an organization with caching.

        Args:
            organization_id: Organization ID for specific overrides

        Returns:
            Maximum parallel file batches (guaranteed to be >= 1)
        """
        cache_key = self._get_cache_key("MAX_PARALLEL_FILE_BATCHES", organization_id)

        # Check cache first
        if self._is_cache_valid(cache_key):
            cached_value = self._config_cache[cache_key]
            logger.debug(
                f"Using cached configuration for org {organization_id}: {cached_value}"
            )
            return cached_value

        try:
            value = self.core_client.get_max_parallel_file_batches(organization_id)
            # Cache the successful result
            self._set_cache(cache_key, value)
            logger.debug(
                f"Using organization configuration for {organization_id}: {value}"
            )
            return value
        except Exception as e:
            logger.warning(f"Failed to get batch size from configuration: {e}")
            # Fallback to environment variable (matching backend)
            import os

            try:
                value = int(
                    os.getenv("MAX_PARALLEL_FILE_BATCHES", "1")
                )  # Match backend default
                value = max(1, value)
                # Cache the fallback value for a shorter time (30 seconds)
                import time

                self._cache_timestamps[cache_key] = time.time() - (self._cache_ttl - 30)
                self._config_cache[cache_key] = value
                return value
            except (ValueError, TypeError):
                env_default = int(os.getenv("MAX_PARALLEL_FILE_BATCHES", "1"))
                logger.warning(
                    f"Invalid MAX_PARALLEL_FILE_BATCHES environment variable, using default {env_default}"
                )
                return env_default

    def get_config_value(
        self,
        config_key: str,
        organization_id: str | None = None,
        default_value: Any | None = None,
    ) -> Any:
        """Get any configuration value for an organization.

        Args:
            config_key: Configuration key name
            organization_id: Organization ID for specific overrides
            default_value: Fallback value if all else fails

        Returns:
            Configuration value with proper type casting
        """
        try:
            return self.core_client.get_config_value(
                config_key=config_key,
                organization_id=organization_id,
                default_value=default_value,
            )
        except Exception as e:
            logger.warning(f"Failed to get config {config_key}: {e}")
            return default_value


# Global configuration client instance (initialized with API client when available)
_global_worker_config_client: WorkerConfigurationClient | None = None


def get_worker_configuration_client(
    api_client: InternalAPIClient | None = None,
) -> WorkerConfigurationClient:
    """Get worker configuration client instance.

    Args:
        api_client: API client to use (creates new instance if provided)

    Returns:
        WorkerConfigurationClient instance
    """
    global _global_worker_config_client

    if api_client:
        # Create new instance with specific API client
        return WorkerConfigurationClient(api_client)

    if _global_worker_config_client is None:
        _global_worker_config_client = WorkerConfigurationClient()

    return _global_worker_config_client


# Convenience functions for common worker operations
def get_max_parallel_file_batches_for_worker(
    organization_id: str | None = None, api_client: InternalAPIClient | None = None
) -> int:
    """Get MAX_PARALLEL_FILE_BATCHES configuration for workers.

    This is the main function workers should use to get organization-specific
    batch size configurations.

    Args:
        organization_id: Organization ID for specific overrides
        api_client: Internal API client for backend communication

    Returns:
        Maximum parallel file batches (guaranteed to be >= 1)
    """
    config_client = get_worker_configuration_client(api_client)
    return config_client.get_max_parallel_file_batches(organization_id)


def get_batch_size_with_fallback(
    organization_id: str | None = None,
    api_client: InternalAPIClient | None = None,
    env_var_name: str = "MAX_PARALLEL_FILE_BATCHES",
    default_value: int | None = None,
) -> int:
    """Get batch size with multiple fallback layers using environment defaults.

    This provides maximum compatibility for existing worker code while
    adding organization-specific configuration support.

    Fallback order:
    1. Organization-specific configuration (if API client available)
    2. Environment variable
    3. Provided default value
    4. Environment variable default (matching backend)

    Args:
        organization_id: Organization ID for specific overrides
        api_client: Internal API client for backend communication
        env_var_name: Environment variable name to check
        default_value: Default value to use as fallback (if None, uses environment default)

    Returns:
        Batch size (guaranteed to be >= 1)
    """
    # Try organization configuration first
    if api_client and organization_id:
        try:
            org_value = get_max_parallel_file_batches_for_worker(
                organization_id, api_client
            )
            logger.info(
                f"Using organization configuration for {organization_id}: {org_value}"
            )
            return org_value
        except Exception as e:
            logger.warning(f"Failed to get organization config, falling back: {e}")

    # Fall back to environment variable
    import os

    try:
        # Use provided default or environment default
        fallback_default = (
            str(default_value) if default_value is not None else "1"
        )  # Match backend
        env_value = int(os.getenv(env_var_name, fallback_default))
        if env_value >= 1:
            logger.info(f"Using environment variable {env_var_name}: {env_value}")
            return env_value
    except (ValueError, TypeError):
        logger.warning(f"Invalid {env_var_name} environment variable")

    # Final fallback to environment default (matching backend)
    try:
        final_value = int(
            os.getenv("MAX_PARALLEL_FILE_BATCHES", "1")
        )  # Match backend default
        final_value = max(1, final_value)
    except (ValueError, TypeError):
        final_value = 1  # Absolute fallback

    logger.info(f"Using final environment fallback: {final_value}")
    return final_value
