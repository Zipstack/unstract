"""Workers Plugin System

This module provides a settings-based plugin architecture for workers that allows
modular functionality to be added without modifying core worker code.

The system automatically loads plugins based on Django settings configuration,
providing clean separation between OSS and cloud plugins.

Architecture:
- OSS: Only basic plugins available (configured in base.py)
- Cloud: Additional cloud plugins loaded via cloud.py settings
- Settings-driven: No hardcoded plugin discovery or try/except imports

Usage:
    from workers.plugins import get_plugin, list_available_plugins

    # Get a specific plugin - automatically loads based on settings
    manual_review = get_plugin("manual_review")  # Available only in cloud

    # List all available plugins - shows only enabled plugins
    plugins = list_available_plugins()
"""

# Import the new settings-based registry system
from ..plugin_registry import (
    get_plugin,
    get_plugin_config,
    initialize_plugins,
    is_plugin_enabled,
    list_available_plugins,
    validate_plugin_structure,
)

# Backward compatibility exports
get_plugin_requirements = get_plugin_config


def load_plugin_tasks(plugin_name: str):
    """Load Celery tasks from a plugin."""
    plugin = get_plugin(plugin_name)
    if plugin and hasattr(plugin, "get_tasks"):
        return plugin.get_tasks()
    return None


def get_all_plugin_tasks():
    """Get all tasks from all enabled plugins."""
    all_tasks = {}

    for plugin_info in list_available_plugins():
        if plugin_info["enabled"]:
            plugin_name = plugin_info["name"]
            tasks = load_plugin_tasks(plugin_name)
            if tasks:
                all_tasks[plugin_name] = tasks

    return all_tasks


__all__ = [
    "get_plugin",
    "list_available_plugins",
    "is_plugin_enabled",
    "get_plugin_requirements",
    "get_plugin_config",
    "initialize_plugins",
    "load_plugin_tasks",
    "get_all_plugin_tasks",
    "validate_plugin_structure",
]
