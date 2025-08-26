"""Client Plugin Registry for Workers

This registry system allows dynamic loading of API client plugins based on
Django settings configuration. This eliminates the need for conditional imports
and try/except blocks while maintaining clean separation between OSS and cloud features.

The registry follows the same pattern as the main plugin registry but is
specifically designed for API client extensions.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class APIClientPlugin:
    """Base class for API client plugins."""

    name: str = ""
    description: str = ""
    version: str = "1.0.0"

    def __init__(self, config: Any):
        """Initialize the plugin with configuration."""
        self.config = config

    def close(self):
        """Clean up plugin resources."""
        pass


class ClientPluginRegistry:
    """Registry for API client plugins loaded from Django settings."""

    def __init__(self):
        self._plugins: dict[str, type[APIClientPlugin]] = {}
        self._instances: dict[str, APIClientPlugin] = {}
        self._initialized = False

    def initialize_from_settings(self):
        """Initialize plugins from environment configuration (Django not required in workers)."""
        if self._initialized:
            return

        try:
            from django.conf import settings

            client_plugins = getattr(settings, "WORKERS_CLIENT_PLUGINS", {})

            for plugin_name, plugin_config in client_plugins.items():
                if not plugin_config.get("enabled", False):
                    continue

                try:
                    self._load_plugin_from_config(plugin_name, plugin_config)
                except Exception as e:
                    logger.warning(f"Failed to load client plugin {plugin_name}: {e}")

        except ImportError as ie:
            # Django not available - try worker-specific initialization
            logger.info(
                f"DEBUG: Django not available (ImportError: {ie}), trying worker-specific plugin initialization"
            )
            self._initialize_worker_plugins()
        except Exception as e:
            logger.warning(f"Failed to initialize client plugins from settings: {e}")
            import traceback

            logger.warning(f"Full traceback: {traceback.format_exc()}")

        logger.info(
            f"DEBUG: Plugin registry initialization complete. Final plugins: {list(self._plugins.keys())}"
        )
        self._initialized = True

    def _initialize_worker_plugins(self):
        """Initialize plugins for workers environment (no Django dependencies)."""
        # Auto-discover plugins from plugin directories
        worker_plugins = self._discover_worker_plugins()

        for plugin_name, plugin_config in worker_plugins.items():
            if not plugin_config.get("enabled", False):
                continue

            try:
                self._load_plugin_from_config_worker(plugin_name, plugin_config)
                logger.debug(f"Loaded worker client plugin: {plugin_name}")
            except Exception as e:
                logger.debug(f"Failed to load worker client plugin {plugin_name}: {e}")

    def _discover_worker_plugins(self) -> dict[str, dict[str, Any]]:
        """Auto-discover plugins from plugin directories."""
        import importlib.util
        import os

        discovered_plugins = {}

        # Get plugins directory
        workers_dir = os.path.dirname(__file__)
        plugins_dir = os.path.join(workers_dir, "plugins")

        if not os.path.exists(plugins_dir):
            logger.debug(f"Plugins directory not found: {plugins_dir}")
            return discovered_plugins

        logger.debug(f"Scanning for plugins in: {plugins_dir}")

        # Scan plugin directories
        for item in os.listdir(plugins_dir):
            plugin_path = os.path.join(plugins_dir, item)

            # Skip files, only process directories
            if not os.path.isdir(plugin_path):
                continue

            # Skip __pycache__ and other system directories
            if item.startswith("__") or item.startswith("."):
                continue

            init_file = os.path.join(plugin_path, "__init__.py")
            if not os.path.exists(init_file):
                logger.debug(f"Skipping {item}: no __init__.py found")
                continue

            try:
                # Load the plugin's __init__.py to check for CLIENT_PLUGIN_CONFIG
                spec = importlib.util.spec_from_file_location(
                    f"plugins.{item}", init_file
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Check if the plugin has CLIENT_PLUGIN_CONFIG
                if hasattr(module, "CLIENT_PLUGIN_CONFIG"):
                    config = module.CLIENT_PLUGIN_CONFIG
                    # Use directory name as plugin name (standard convention)
                    discovered_plugins[item] = config
                    logger.debug(f"Discovered plugin: {item} with config: {config}")
                else:
                    logger.debug(f"Plugin {item} has no CLIENT_PLUGIN_CONFIG, skipping")

            except Exception as e:
                logger.debug(f"Failed to load plugin {item}: {e}")

        logger.debug(
            f"Discovered {len(discovered_plugins)} plugins: {list(discovered_plugins.keys())}"
        )
        return discovered_plugins

    def _load_plugin_from_config_worker(self, plugin_name: str, config: dict[str, Any]):
        """Load a plugin from configuration for workers (handles relative imports better)."""
        plugin_path = config.get("plugin_path")
        if not plugin_path:
            raise ValueError(f"Plugin {plugin_name} missing plugin_path")

        try:
            # For workers, use importlib with proper path handling
            import importlib
            import os

            # Convert plugin path to file path
            module_path, class_name = plugin_path.rsplit(".", 1)
            relative_path = module_path.replace(".", os.sep) + ".py"

            # Get absolute path from workers directory
            workers_dir = os.path.dirname(__file__)
            plugin_file_path = os.path.join(workers_dir, relative_path)

            if os.path.exists(plugin_file_path):
                # Use importlib.util for file-based import
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    module_path, plugin_file_path
                )
                module = importlib.util.module_from_spec(spec)

                # Execute the module to load the class
                spec.loader.exec_module(module)
                plugin_class = getattr(module, class_name)

                # Validate plugin class
                if not issubclass(plugin_class, APIClientPlugin):
                    raise TypeError(
                        f"Plugin {plugin_name} must inherit from APIClientPlugin"
                    )

                # Register the plugin class
                self._plugins[plugin_name] = plugin_class
                logger.debug(
                    f"Successfully loaded plugin class {class_name} from {plugin_file_path}"
                )
            else:
                logger.debug(f"Plugin file not found: {plugin_file_path}")

        except Exception as e:
            logger.debug(f"Failed to load plugin {plugin_name} using worker loader: {e}")
            # Fall back to standard import if file-based loading fails
            try:
                module_path, class_name = plugin_path.rsplit(".", 1)
                module = __import__(module_path, fromlist=[class_name])
                plugin_class = getattr(module, class_name)

                if not issubclass(plugin_class, APIClientPlugin):
                    raise TypeError(
                        f"Plugin {plugin_name} must inherit from APIClientPlugin"
                    )

                self._plugins[plugin_name] = plugin_class
                logger.debug(f"Loaded plugin {plugin_name} using fallback import")
            except Exception as fallback_error:
                raise Exception(
                    f"Both file-based and import-based loading failed: {e}, {fallback_error}"
                )

    def _load_plugin_from_config(self, plugin_name: str, config: dict[str, Any]):
        """Load a plugin from configuration."""
        plugin_path = config.get("plugin_path")
        if not plugin_path:
            raise ValueError(f"Plugin {plugin_name} missing plugin_path")

        # Import the plugin module
        module_path, class_name = plugin_path.rsplit(".", 1)
        module = __import__(module_path, fromlist=[class_name])
        plugin_class = getattr(module, class_name)

        # Validate plugin class
        if not issubclass(plugin_class, APIClientPlugin):
            raise TypeError(f"Plugin {plugin_name} must inherit from APIClientPlugin")

        # Register the plugin class
        self._plugins[plugin_name] = plugin_class

    def register_plugin_class(self, name: str, plugin_class: type[APIClientPlugin]):
        """Manually register a plugin class."""
        if not issubclass(plugin_class, APIClientPlugin):
            raise TypeError(f"Plugin {name} must inherit from APIClientPlugin")

        self._plugins[name] = plugin_class
        logger.debug(f"Manually registered client plugin: {name}")

    def get_plugin_instance(
        self, name: str, config: Any = None
    ) -> APIClientPlugin | None:
        """Get or create a plugin instance."""
        self.initialize_from_settings()

        # Return cached instance if available
        if name in self._instances:
            return self._instances[name]

        # Create new instance if plugin class is registered
        if name in self._plugins:
            try:
                plugin_class = self._plugins[name]
                instance = plugin_class(config)
                self._instances[name] = instance
                logger.debug(f"Created instance for client plugin: {name}")
                return instance
            except Exception as e:
                logger.error(f"Failed to create instance for client plugin {name}: {e}")
                return None

        return None

    def has_plugin(self, name: str) -> bool:
        """Check if a plugin is available."""
        self.initialize_from_settings()
        return name in self._plugins

    def list_available_plugins(self) -> list[dict[str, Any]]:
        """List all available client plugins."""
        self.initialize_from_settings()

        plugins = []
        for name, plugin_class in self._plugins.items():
            plugins.append(
                {
                    "name": name,
                    "description": getattr(plugin_class, "description", ""),
                    "version": getattr(plugin_class, "version", "1.0.0"),
                    "enabled": True,
                }
            )

        return plugins

    def close_all_instances(self):
        """Close all plugin instances."""
        for instance in self._instances.values():
            try:
                instance.close()
            except Exception as e:
                logger.warning(f"Error closing client plugin instance: {e}")

        self._instances.clear()

    def clear(self):
        """Clear all plugins and instances."""
        self.close_all_instances()
        self._plugins.clear()
        self._initialized = False


# Global registry instance
_client_plugin_registry = ClientPluginRegistry()


def get_client_plugin(name: str, config: Any = None) -> APIClientPlugin | None:
    """Get a client plugin instance by name."""
    return _client_plugin_registry.get_plugin_instance(name, config)


def has_client_plugin(name: str) -> bool:
    """Check if a client plugin is available."""
    return _client_plugin_registry.has_plugin(name)


def list_client_plugins() -> list[dict[str, Any]]:
    """List all available client plugins."""
    return _client_plugin_registry.list_available_plugins()


def register_client_plugin(name: str, plugin_class: type[APIClientPlugin]):
    """Register a client plugin class."""
    _client_plugin_registry.register_plugin_class(name, plugin_class)


def close_all_client_plugins():
    """Close all client plugin instances."""
    _client_plugin_registry.close_all_instances()


def initialize_client_plugins():
    """Initialize client plugins from settings."""
    _client_plugin_registry.initialize_from_settings()
