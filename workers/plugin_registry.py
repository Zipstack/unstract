"""Workers Plugin Registry System

This registry system allows dynamic loading of worker plugins based on Django
settings configuration, providing clean separation between OSS and cloud plugins.

Architecture:
- OSS: Only basic/OSS plugins are available
- Cloud: Additional cloud plugins are registered via WORKERS_PLUGIN_MODULES setting
- No hardcoded imports - everything is settings-driven
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WorkersPluginRegistry:
    """Registry for managing worker plugins dynamically based on settings."""

    def __init__(self):
        self._plugins: dict[str, Any] = {}
        self._plugin_configs: dict[str, dict[str, Any]] = {}
        self._initialized = False

    def register_plugin_from_config(self, name: str, config: dict[str, Any]) -> None:
        """Register a plugin from configuration.

        Args:
            name: Plugin name
            config: Plugin configuration dictionary
        """
        if not config.get("enabled", True):
            logger.debug(f"Plugin '{name}' disabled, skipping registration")
            return

        if name in self._plugin_configs:
            logger.warning(f"Plugin '{name}' already registered, skipping")
            return

        # Store configuration
        self._plugin_configs[name] = config

        # Try to load plugin
        plugin_path = config.get("plugin_path")
        if plugin_path:
            self._load_plugin_module(name, plugin_path)

        logger.info(f"Registered plugin: {name}")

    def _load_plugin_module(self, name: str, plugin_path: str) -> None:
        """Load a plugin module dynamically.

        Args:
            name: Plugin name
            plugin_path: Python module path (e.g., "workers.plugins.manual_review")
        """
        try:
            # Import the plugin module
            module = __import__(plugin_path, fromlist=[""])

            # Look for a Plugin class or client
            plugin_instance = None

            if hasattr(module, "Plugin"):
                plugin_instance = module.Plugin()
            elif hasattr(module, "ManualReviewClient"):
                plugin_instance = module.ManualReviewClient
            else:
                # Store the module itself
                plugin_instance = module

            self._plugins[name] = plugin_instance
            logger.debug(f"Loaded plugin module: {name} from {plugin_path}")

        except ImportError as e:
            logger.warning(f"Could not import plugin '{name}' from {plugin_path}: {e}")
        except Exception as e:
            logger.error(f"Error loading plugin '{name}': {e}")

    def get_plugin(self, name: str) -> Any | None:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def list_available_plugins(self) -> list[dict[str, Any]]:
        """List all available plugins with their configurations."""
        plugins = []
        for name, config in self._plugin_configs.items():
            plugin_info = {
                "name": name,
                "enabled": config.get("enabled", True),
                "description": config.get("description", ""),
                "version": config.get("version", "unknown"),
                "loaded": name in self._plugins,
            }
            plugins.append(plugin_info)
        return plugins

    def is_plugin_enabled(self, name: str) -> bool:
        """Check if a plugin is enabled."""
        config = self._plugin_configs.get(name, {})
        return config.get("enabled", False)

    def get_plugin_config(self, name: str) -> dict[str, Any]:
        """Get plugin configuration."""
        return self._plugin_configs.get(name, {})

    def initialize_from_settings(self) -> None:
        """Initialize plugins from Django settings or environment.

        This method attempts to load Django settings first, then falls back
        to environment variables or default configuration.
        """
        if self._initialized:
            return

        plugin_modules = {}

        # Try to load from Django settings
        try:
            from django.conf import settings

            plugin_modules = getattr(settings, "WORKERS_PLUGIN_MODULES", {})
            logger.info(
                f"Loaded plugin configuration from Django settings: {len(plugin_modules)} modules"
            )
        except (ImportError, Exception) as e:
            logger.debug(f"Could not load Django settings: {e}")

            # Fallback to environment variables or defaults
            plugin_modules = self._get_default_plugin_config()

        # Register all configured plugins
        for name, config in plugin_modules.items():
            self.register_plugin_from_config(name, config)

        self._initialized = True
        logger.info(
            f"Plugin registry initialized with {len(self._plugin_configs)} plugins"
        )

    def _get_default_plugin_config(self) -> dict[str, Any]:
        """Get default plugin configuration when Django settings are not available."""
        # This provides minimal fallback configuration
        default_config = {}

        # Check if we're in a cloud environment via environment variables
        if os.environ.get("CLOUD_DEPLOYMENT", "false").lower() == "true":
            default_config.update(
                {
                    "manual_review": {
                        "enabled": True,
                        "plugin_path": "workers.plugins.manual_review",
                        "description": "Manual review system",
                        "version": "1.0.0",
                    }
                }
            )

        return default_config

    def clear(self) -> None:
        """Clear all plugins (for testing)."""
        self._plugins.clear()
        self._plugin_configs.clear()
        self._initialized = False


# Global registry instance
_workers_plugin_registry = WorkersPluginRegistry()


def get_plugin(name: str) -> Any | None:
    """Get a plugin by name.

    This automatically initializes the registry from settings if needed.
    """
    _workers_plugin_registry.initialize_from_settings()
    return _workers_plugin_registry.get_plugin(name)


def list_available_plugins() -> list[dict[str, Any]]:
    """List all available plugins."""
    _workers_plugin_registry.initialize_from_settings()
    return _workers_plugin_registry.list_available_plugins()


def is_plugin_enabled(name: str) -> bool:
    """Check if a plugin is enabled."""
    _workers_plugin_registry.initialize_from_settings()
    return _workers_plugin_registry.is_plugin_enabled(name)


def get_plugin_config(name: str) -> dict[str, Any]:
    """Get plugin configuration."""
    _workers_plugin_registry.initialize_from_settings()
    return _workers_plugin_registry.get_plugin_config(name)


def initialize_plugins() -> None:
    """Explicitly initialize plugins from settings."""
    _workers_plugin_registry.initialize_from_settings()


# Backward compatibility - expose the old plugin system functions
def validate_plugin_structure(plugin_name: str) -> dict[str, bool]:
    """Validate plugin structure (backward compatibility)."""
    config = get_plugin_config(plugin_name)
    plugin_path = config.get("plugin_path", "")

    if not plugin_path:
        return {"exists": False}

    # Convert module path to file path for validation
    try:
        module_parts = plugin_path.split(".")
        if len(module_parts) >= 3 and module_parts[0] == "workers":
            # e.g. workers.plugins.manual_review -> workers/plugins/manual_review
            plugin_dir = Path(__file__).parent / "/".join(module_parts[1:])

            return {
                "exists": plugin_dir.exists(),
                "has_init": (plugin_dir / "__init__.py").exists(),
                "has_client": (plugin_dir / "client.py").exists(),
                "has_tasks": (plugin_dir / "tasks.py").exists(),
                "has_dto": (plugin_dir / "dto.py").exists(),
                "has_readme": (plugin_dir / "README.md").exists(),
            }
    except Exception:
        pass

    return {"exists": False}


__all__ = [
    "get_plugin",
    "list_available_plugins",
    "is_plugin_enabled",
    "get_plugin_config",
    "initialize_plugins",
    "validate_plugin_structure",
    "WorkersPluginRegistry",
]
