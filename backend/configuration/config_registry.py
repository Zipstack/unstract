"""Configuration registry for dynamically loading configuration keys.

This module handles loading both base OSS configuration keys and
cloud-specific configuration keys from plugins when available.
"""

import logging
from importlib import import_module
from typing import Any

from configuration.constants import ConfigPluginConstants
from configuration.enums import ConfigKey, ConfigSpec

logger = logging.getLogger(__name__)


def _load_cloud_config_specs() -> dict[str, ConfigSpec]:
    """Load cloud configuration specs from plugins if available.

    Returns:
        Dictionary of cloud configuration specs, empty if plugin not available.
    """
    cloud_specs = {}

    try:
        from plugins import get_plugin

        # Try to get the configuration plugin
        plugin = get_plugin(ConfigPluginConstants.CONFIG_PLUGIN_DIR)

        if not plugin:
            logger.debug("Configuration plugin not found")
            return cloud_specs

        # Check if plugin is active
        metadata = plugin.get(ConfigPluginConstants.METADATA, {})
        if not metadata.get(ConfigPluginConstants.METADATA_IS_ACTIVE, False):
            logger.warning("Cloud configuration plugin is not active")
            return cloud_specs

        # Get the plugin module and import the config specs submodule
        plugin_module = plugin.get("module")
        if not plugin_module:
            logger.warning("Configuration plugin module not found")
            return cloud_specs

        # Import the cloud_config submodule to get config specs
        base_module = (
            getattr(plugin_module, "__package__", None) or plugin_module.__name__
        )
        config_module_path = f"{base_module}.{ConfigPluginConstants.CONFIG_MODULE}"
        config_module = import_module(config_module_path)
        config_specs = getattr(config_module, ConfigPluginConstants.CONFIG_SPECS, {})

        cloud_specs.update(config_specs)
        logger.info(
            "Loaded cloud configuration plugin: %s with %d config keys",
            metadata.get(ConfigPluginConstants.METADATA_NAME, "Unknown"),
            len(config_specs),
        )

    except ImportError as e:
        logger.debug("Could not import plugins module: %s", e)
    except Exception as e:
        logger.error("Error loading cloud configuration plugin: %s", e)

    return cloud_specs


class ConfigurationRegistry:
    """Registry for managing all configuration keys (OSS and cloud).

    This registry provides a unified interface to access both base OSS
    configuration keys and cloud-specific keys when available.
    """

    # Cache for all config specs (loaded once)
    _all_config_specs: dict[str, ConfigSpec] | None = None

    @classmethod
    def _load_all_specs(cls) -> dict[str, ConfigSpec]:
        """Load all configuration specs (OSS + cloud).

        Returns:
            Dictionary mapping config key names to ConfigSpec objects.
        """
        if cls._all_config_specs is not None:
            return cls._all_config_specs

        all_specs = {}

        # First, add all OSS config keys
        for config_key in ConfigKey:
            all_specs[config_key.name] = config_key.value

        # Then, add cloud config keys if available
        cloud_specs = _load_cloud_config_specs()
        all_specs.update(cloud_specs)

        # Cache the result
        cls._all_config_specs = all_specs
        logger.info("Configuration registry loaded with %d total keys", len(all_specs))

        return all_specs

    @classmethod
    def get_config_spec(cls, key_name: str) -> ConfigSpec | None:
        """Get configuration spec for a given key name.

        Args:
            key_name: Name of the configuration key (e.g., "ENABLE_HIGHLIGHT_API_DEPLOYMENT")

        Returns:
            ConfigSpec object if found, None otherwise.
        """
        all_specs = cls._load_all_specs()
        return all_specs.get(key_name)

    @classmethod
    def get_all_config_keys(cls) -> dict[str, ConfigSpec]:
        """Get all available configuration keys.

        Returns:
            Dictionary of all configuration specs (OSS + cloud).
        """
        return cls._load_all_specs().copy()

    @classmethod
    def is_config_key_available(cls, key_name: str) -> bool:
        """Check if a configuration key is available.

        Args:
            key_name: Name of the configuration key.

        Returns:
            True if the key exists, False otherwise.
        """
        return key_name in cls._load_all_specs()

    @classmethod
    def cast_value(cls, key_name: str, raw_value: Any) -> Any:
        """Cast a raw value to the appropriate type for a config key.

        Args:
            key_name: Name of the configuration key.
            raw_value: Raw value to cast.

        Returns:
            Casted value according to the ConfigSpec.

        Raises:
            ValueError: If key not found or casting fails.
        """
        spec = cls.get_config_spec(key_name)
        if not spec:
            raise ValueError(f"Configuration key '{key_name}' not found")

        # Try to use ConfigKey enum's cast_value if it's an OSS key
        try:
            config_key = ConfigKey[key_name]
            return config_key.cast_value(raw_value)
        except KeyError:
            # It's a cloud key, cast it manually
            from configuration.enums import ConfigType

            converters = {
                ConfigType.INT: int,
                ConfigType.BOOL: lambda v: v.lower() in ("true", "1")
                if isinstance(v, str)
                else bool(v),
                ConfigType.JSON: lambda v: __import__("json").loads(v),
                ConfigType.STRING: str,
            }

            converter = converters.get(spec.value_type)
            if not converter:
                raise ValueError(f"Unknown value type: {spec.value_type}")

            try:
                converted_value = converter(raw_value)
                # Validate min/max if applicable
                if (
                    hasattr(spec, "min_value")
                    and spec.min_value is not None
                    and converted_value < spec.min_value
                ):
                    raise ValueError(
                        f"Value {converted_value} is below minimum {spec.min_value}"
                    )
                if (
                    hasattr(spec, "max_value")
                    and spec.max_value is not None
                    and converted_value > spec.max_value
                ):
                    raise ValueError(
                        f"Value {converted_value} is above maximum {spec.max_value}"
                    )
                return converted_value
            except Exception as e:
                raise ValueError(f"Failed to cast value '{raw_value}': {e}")
