"""Django-specific plugin manager wrapper.

This module provides Django integration for the generic PluginManager,
handling Django-specific features like app registry integration and Django
logging.
"""

import logging
from pathlib import Path
from typing import Any

from unstract.core.plugins import PluginManager as GenericPluginManager


class DjangoPluginManager:
    """Django-specific plugin manager wrapper.

    Wraps the generic PluginManager with Django-specific functionality like
    Django app integration and logging.
    """

    _instance = None

    def __new__(
        cls,
        plugins_dir: Path | str,
        plugins_pkg: str,
        logger: logging.Logger | None = None,
    ) -> "DjangoPluginManager":
        """Create or return the singleton DjangoPluginManager instance.

        Args:
            plugins_dir: Directory containing plugins
            plugins_pkg: Python package path for plugins (e.g., 'myapp.plugins')
            logger: Logger instance (defaults to module logger)

        Returns:
            DjangoPluginManager singleton instance
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False

        # Initialize or update plugin manager if parameters change
        if plugins_dir and plugins_pkg:
            plugins_dir_path = (
                Path(plugins_dir) if isinstance(plugins_dir, str) else plugins_dir
            )

            if (
                not cls._instance._initialized
                or cls._instance._plugins_dir != plugins_dir_path
                or cls._instance._plugins_pkg != plugins_pkg
            ):
                cls._instance._plugins_dir = plugins_dir_path
                cls._instance._plugins_pkg = plugins_pkg
                cls._instance._logger = logger or logging.getLogger(__name__)
                cls._instance._init_manager()

        return cls._instance

    def _init_manager(self) -> None:
        """Initialize the generic plugin manager."""
        self._manager = GenericPluginManager(
            plugins_dir=self._plugins_dir,
            plugins_pkg=self._plugins_pkg,
            logger=self._logger,
            use_singleton=True,
            registration_callback=None,  # Django doesn't need special registration
        )
        self._initialized = True

    def load_plugins(self) -> None:
        """Load plugins using the generic manager."""
        if not self._initialized:
            raise RuntimeError(
                "DjangoPluginManager not initialized. "
                "Call with plugins_dir and plugins_pkg first."
            )
        self._manager.load_plugins()

    def get_plugin(self, name: str) -> dict[str, Any]:
        """Get plugin metadata by name.

        Args:
            name: Plugin name to retrieve

        Returns:
            Dictionary containing plugin metadata
        """
        if not self._initialized:
            return {}
        return self._manager.get_plugin(name)

    def has_plugin(self, name: str) -> bool:
        """Check if a plugin is loaded.

        Args:
            name: Plugin name to check

        Returns:
            bool: True if plugin exists
        """
        if not self._initialized:
            return False
        return self._manager.has_plugin(name)

    def get_all_plugins(self) -> dict[str, dict[str, Any]]:
        """Get all loaded plugins.

        Returns:
            Dictionary mapping plugin names to their metadata
        """
        if not self._initialized:
            return {}
        return self._manager.get_all_plugins()

    @property
    def plugins(self) -> dict[str, dict[str, Any]]:
        """Get all loaded plugins."""
        return self.get_all_plugins()


# Maintain backward compatibility with common class name
PluginManager = DjangoPluginManager


def plugin_loader(
    plugins_dir: Path | str,
    plugins_pkg: str,
    logger: logging.Logger | None = None,
) -> DjangoPluginManager:
    """Load plugins for a Django application.

    Convenience function to create a DjangoPluginManager instance and load plugins.

    Args:
        plugins_dir: Directory containing plugins
        plugins_pkg: Python package path for plugins (e.g., 'backend.plugins')
        logger: Logger instance (optional)

    Returns:
        DjangoPluginManager: The plugin manager instance

    Example:
        # In your Django app initialization (e.g., apps.py or __init__.py):
        from pathlib import Path
        from unstract.core.django import plugin_loader

        # Load plugins from backend/plugins directory
        plugins_dir = Path(__file__).parent / 'plugins'
        manager = plugin_loader(plugins_dir, 'backend.plugins')
        manager.load_plugins()

        # Later, check for plugins:
        if manager.has_plugin('subscription_usage'):
            plugin = manager.get_plugin('subscription_usage')
            service = plugin['service_class']()
            service.commit_usage(...)
    """
    manager = DjangoPluginManager(plugins_dir, plugins_pkg, logger)
    manager.load_plugins()
    return manager
