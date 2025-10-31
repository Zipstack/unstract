"""Backend plugins initialization.

This module initializes the Django plugin manager for all backend plugins.
"""

import logging
from pathlib import Path

from unstract.core.django import DjangoPluginManager

logger = logging.getLogger(__name__)

# Initialize plugin manager singleton
_plugin_manager = None


def get_plugin_manager() -> DjangoPluginManager:
    """Get or initialize the plugin manager singleton.

    Note: Plugins are loaded by PluginsConfig.ready() after Django initialization.
    This function only creates the manager instance without loading plugins.

    Returns:
        DjangoPluginManager: The plugin manager instance
    """
    global _plugin_manager
    if _plugin_manager is None:
        plugins_dir = Path(__file__).parent
        _plugin_manager = DjangoPluginManager(
            plugins_dir=plugins_dir,
            plugins_pkg="plugins",
            logger=logger,
        )
    return _plugin_manager


def get_plugin(plugin_name: str) -> dict:
    """Get plugin metadata by name (simplified single-line access).

    This is a convenience function that combines get_plugin_manager()
    and plugin_manager.get_plugin() into one call.

    Args:
        plugin_name: Name of the plugin to retrieve

    Returns:
        Dictionary containing plugin metadata (version, module, service_class, etc.)
        or empty dict if plugin not found

    Example:
        >>> from plugins import get_plugin
        >>> plugin = get_plugin("subscription_usage")
        >>> if plugin:
        ...     service = plugin["service_class"]()
    """
    manager = get_plugin_manager()
    return manager.get_plugin(plugin_name)


__all__ = ["get_plugin_manager", "get_plugin"]
