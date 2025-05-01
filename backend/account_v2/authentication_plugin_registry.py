import importlib
import logging
from typing import Dict, List, Optional, Type

from account_v2.authentication_plugin import AuthenticationPlugin
from account_v2.authentication_plugin_config import AuthenticationPluginConfig
from account_v2.authentication_plugin_registry_config import AuthenticationPluginRegistryConfig
from account_v2.exceptions import AuthenticationPluginNotFound

logger = logging.getLogger(__name__)


class AuthenticationPluginRegistry:
    """Registry for authentication plugins."""

    def __init__(self, config: AuthenticationPluginRegistryConfig):
        """Initialize the registry.

        Args:
            config: The registry configuration.
        """
        self._config = config
        self._plugins: Dict[str, Type[AuthenticationPlugin]] = {}
        self._load_plugins()

    def _load_plugins(self) -> None:
        """Load all plugins from the configuration."""
        for plugin_config in self._config.plugins:
            try:
                self._load_plugin(plugin_config)
            except Exception:
                logger.exception(
                    "Failed to load authentication plugin %s", plugin_config.name
                )

    def _load_plugin(self, plugin_config: AuthenticationPluginConfig) -> None:
        """Load a plugin from the configuration.

        Args:
            plugin_config: The plugin configuration.
        """
        # Define a whitelist of allowed modules for security
        allowed_modules = {
            "account_v2.authentication_plugins.basic",
            "account_v2.authentication_plugins.jwt",
            "account_v2.authentication_plugins.oauth",
            "account_v2.authentication_plugins.saml",
            # Add other legitimate authentication plugin modules here
        }
        
        module_path = plugin_config.module_path
        
        if module_path not in allowed_modules:
            logger.error(f"Attempted to load unauthorized module: {module_path}")
            return
            
        try:
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, plugin_config.class_name)
            self._plugins[plugin_config.name] = plugin_class
        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to import plugin {plugin_config.name}: {str(e)}")
            raise

    def get_plugin(self, name: str) -> Optional[Type[AuthenticationPlugin]]:
        """Get a plugin by name.

        Args:
            name: The name of the plugin.

        Returns:
            The plugin class, or None if not found.
        """
        return self._plugins.get(name)

    def get_plugin_names(self) -> List[str]:
        """Get all plugin names.

        Returns:
            A list of plugin names.
        """
        return list(self._plugins.keys())

    def get_plugin_or_raise(self, name: str) -> Type[AuthenticationPlugin]:
        """Get a plugin by name, or raise an exception if not found.

        Args:
            name: The name of the plugin.

        Returns:
            The plugin class.

        Raises:
            AuthenticationPluginNotFound: If the plugin is not found.
        """
        plugin = self.get_plugin(name)
        if plugin is None:
            raise AuthenticationPluginNotFound(name)
        return plugin
