"""Configuration Client for Workers

This module provides a Django-independent way for workers to access organization-specific
configurations. It mirrors the backend's Configuration.get_value_by_organization() functionality
but works through API calls instead of direct database access.

Usage:
    # In worker code
    config_client = ConfigurationClient(api_client)
    batch_size = config_client.get_config_value(
        config_key="MAX_PARALLEL_FILE_BATCHES",
        organization_id=organization_id,
        default_value=5  # fallback if API fails
    )
"""

import logging
import os
from typing import Any


# Simple response class for configuration client
class ConfigurationResponse:
    def __init__(self, success: bool, data: dict = None, error: str = None):
        self.success = success
        self.data = data or {}
        self.error = error


logger = logging.getLogger(__name__)


class ConfigurationSpec:
    """Configuration specification matching backend ConfigSpec."""

    def __init__(
        self,
        default: Any,
        value_type: str,
        help_text: str,
        min_value: Any | None = None,
        max_value: Any | None = None,
    ):
        self.default = default
        self.value_type = value_type
        self.help_text = help_text
        self.min_value = min_value
        self.max_value = max_value


class ConfigKey:
    """Configuration keys matching backend ConfigKey enum."""

    MAX_PARALLEL_FILE_BATCHES = "MAX_PARALLEL_FILE_BATCHES"

    # Registry of known config specs (from environment defaults matching backend)
    _SPECS = {
        MAX_PARALLEL_FILE_BATCHES: ConfigurationSpec(
            default=int(
                os.getenv("MAX_PARALLEL_FILE_BATCHES", "1")
            ),  # Match backend default
            value_type="int",
            help_text="Maximum number of parallel file processing batches",
            min_value=1,
            max_value=int(
                os.getenv("MAX_PARALLEL_FILE_BATCHES_MAX_VALUE", "100")
            ),  # Match backend
        ),
    }

    @classmethod
    def get_spec(cls, key: str) -> ConfigurationSpec | None:
        """Get configuration spec for a key."""
        return cls._SPECS.get(key)

    @classmethod
    def get_default(cls, key: str) -> Any:
        """Get default value for a configuration key."""
        spec = cls.get_spec(key)
        return spec.default if spec else None


class ConfigurationClient:
    """Client for accessing organization-specific configurations in workers.

    This class provides a Django-independent way to access the same configuration
    system that the backend uses, but through API calls instead of direct DB access.
    """

    def __init__(self, api_client=None):
        """Initialize configuration client.

        Args:
            api_client: Internal API client for backend communication (optional)
        """
        self.api_client = api_client
        self._cache = {}  # Simple in-memory cache for config values

    def get_config_value(
        self,
        config_key: str,
        organization_id: str | None = None,
        default_value: Any | None = None,
        use_cache: bool = True,
    ) -> Any:
        """Get configuration value for an organization with fallback to defaults.

        This method mirrors the backend's Configuration.get_value_by_organization() logic:
        1. Try to get organization-specific override from API
        2. Fall back to config registry default
        3. Fall back to provided default_value
        4. Fall back to environment variable or hardcoded fallback

        Args:
            config_key: The configuration key name (e.g., "MAX_PARALLEL_FILE_BATCHES")
            organization_id: Organization ID for specific overrides
            default_value: Fallback value if all else fails
            use_cache: Whether to use cached values (default: True)

        Returns:
            The configuration value with proper type casting
        """
        cache_key = f"{organization_id}:{config_key}" if organization_id else config_key

        # Check cache first
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        # Get the spec for validation and defaults
        spec = ConfigKey.get_spec(config_key)
        registry_default = spec.default if spec else default_value

        # Try to get organization-specific value via API
        if self.api_client and organization_id:
            try:
                api_value = self._get_config_from_api(config_key, organization_id)
                if api_value is not None:
                    # Type cast and validate the API response
                    typed_value = self._cast_and_validate_value(
                        config_key, api_value, spec
                    )
                    if typed_value is not None:
                        if use_cache:
                            self._cache[cache_key] = typed_value
                        return typed_value
            except Exception as e:
                logger.warning(f"Failed to get config {config_key} from API: {e}")

        # Fall back to registry default
        if registry_default is not None:
            if use_cache:
                self._cache[cache_key] = registry_default
            return registry_default

        # Final fallback to provided default
        if default_value is not None:
            if use_cache:
                self._cache[cache_key] = default_value
            return default_value

        # Last resort: environment variable defaults (matching backend)
        env_defaults = {
            ConfigKey.MAX_PARALLEL_FILE_BATCHES: int(
                os.getenv("MAX_PARALLEL_FILE_BATCHES", "1")
            ),
        }

        final_value = env_defaults.get(config_key)
        if final_value is not None:
            logger.info(f"Using environment default for {config_key}: {final_value}")
            if use_cache:
                self._cache[cache_key] = final_value

        return final_value

    def _get_config_from_api(self, config_key: str, organization_id: str) -> Any:
        """Get configuration value from backend API.

        Args:
            config_key: Configuration key name
            organization_id: Organization ID

        Returns:
            Configuration value from API or None if not found/error
        """
        if not self.api_client:
            return None

        try:
            # Call internal API endpoint for configuration
            response = self.api_client.get(
                f"/internal/configuration/{config_key}/",
                params={"organization_id": organization_id},
            )

            if response.success and response.data:
                return response.data.get("value")

        except Exception as e:
            logger.debug(f"API call failed for config {config_key}: {e}")

        return None

    def _cast_and_validate_value(
        self, config_key: str, raw_value: Any, spec: ConfigurationSpec | None
    ) -> Any | None:
        """Cast raw value to proper type and validate constraints.

        Args:
            config_key: Configuration key name
            raw_value: Raw value from API
            spec: Configuration specification

        Returns:
            Typed and validated value or None if invalid
        """
        if not spec:
            return raw_value  # Return as-is if no spec available

        try:
            # Type casting
            if spec.value_type == "int":
                typed_value = int(raw_value)
            elif spec.value_type == "bool":
                if isinstance(raw_value, str):
                    typed_value = raw_value.lower() in ("true", "1", "yes", "on")
                else:
                    typed_value = bool(raw_value)
            elif spec.value_type == "json":
                import json

                typed_value = (
                    json.loads(raw_value) if isinstance(raw_value, str) else raw_value
                )
            else:  # string or unknown
                typed_value = str(raw_value)

            # Validation constraints
            if spec.min_value is not None and typed_value < spec.min_value:
                logger.warning(
                    f"Config {config_key} value {typed_value} below minimum {spec.min_value}, using default"
                )
                return None

            if spec.max_value is not None and typed_value > spec.max_value:
                logger.warning(
                    f"Config {config_key} value {typed_value} above maximum {spec.max_value}, using default"
                )
                return None

            return typed_value

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to cast config {config_key} value '{raw_value}': {e}")
            return None

    def get_max_parallel_file_batches(self, organization_id: str | None = None) -> int:
        """Convenience method to get MAX_PARALLEL_FILE_BATCHES configuration.

        Args:
            organization_id: Organization ID for specific overrides

        Returns:
            Maximum parallel file batches (guaranteed to be >= 1)
        """
        value = self.get_config_value(
            config_key=ConfigKey.MAX_PARALLEL_FILE_BATCHES,
            organization_id=organization_id,
            default_value=int(
                os.getenv("MAX_PARALLEL_FILE_BATCHES", "1")
            ),  # Match backend default
        )

        # Ensure it's a valid positive integer
        try:
            int_value = int(value)
            return max(1, int_value)  # Ensure minimum of 1
        except (ValueError, TypeError):
            default_batch_size = int(os.getenv("MAX_PARALLEL_FILE_BATCHES", "1"))
            logger.warning(
                f"Invalid batch size value: {value}, using environment default {default_batch_size}"
            )
            return default_batch_size

    def clear_cache(self, organization_id: str | None = None) -> None:
        """Clear cached configuration values.

        Args:
            organization_id: Clear cache only for specific organization, or all if None
        """
        if organization_id:
            # Clear only keys for specific organization
            keys_to_remove = [
                key for key in self._cache.keys() if key.startswith(f"{organization_id}:")
            ]
            for key in keys_to_remove:
                del self._cache[key]
        else:
            # Clear all cached values
            self._cache.clear()

    def get_all_cached_values(self) -> dict[str, Any]:
        """Get all cached configuration values (for debugging/monitoring).

        Returns:
            Dictionary of all cached configuration values
        """
        return self._cache.copy()


# Global configuration client instance (can be initialized with API client)
_global_config_client: ConfigurationClient | None = None


def get_configuration_client(api_client=None) -> ConfigurationClient:
    """Get global configuration client instance.

    Args:
        api_client: API client to use (creates new instance if provided)

    Returns:
        ConfigurationClient instance
    """
    global _global_config_client

    if api_client:
        # Create new instance with specific API client
        return ConfigurationClient(api_client)

    if _global_config_client is None:
        _global_config_client = ConfigurationClient()

    return _global_config_client


# Convenience functions for common configurations
def get_max_parallel_file_batches(
    organization_id: str | None = None, api_client=None
) -> int:
    """Get MAX_PARALLEL_FILE_BATCHES configuration value.

    Args:
        organization_id: Organization ID for specific overrides
        api_client: API client for backend communication

    Returns:
        Maximum parallel file batches (guaranteed to be >= 1)
    """
    config_client = get_configuration_client(api_client)
    return config_client.get_max_parallel_file_batches(organization_id)
