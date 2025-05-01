import importlib
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from unstract.prompt_service.helpers.allowed_plugins import is_plugin_allowed
from unstract.prompt_service.models.plugin import Plugin

logger = logging.getLogger(__name__)


def get_plugin_class(plugin_name: str) -> Any:
    """
    Get the plugin class from the plugin name.

    Args:
        plugin_name: The name of the plugin to get the class for

    Returns:
        The plugin class
    """
    try:
        if not is_plugin_allowed(plugin_name):
            logger.error(f"Plugin {plugin_name} is not in the allowed list")
            raise ImportError(f"Plugin {plugin_name} is not allowed")
            
        module = importlib.import_module(plugin_name)
        return module.PluginClass
    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to import plugin {plugin_name}: {e}")
        raise


def get_plugin_instance(
    plugin_name: str, plugin_config: Optional[Dict[str, Any]] = None
) -> Plugin:
    """
    Get an instance of the plugin.

    Args:
        plugin_name: The name of the plugin to get an instance of
        plugin_config: The configuration for the plugin

    Returns:
        An instance of the plugin
    """
    plugin_class = get_plugin_class(plugin_name)
    return plugin_class(plugin_config or {})
