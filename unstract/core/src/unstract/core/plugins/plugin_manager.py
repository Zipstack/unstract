"""Framework-agnostic plugin manager for loading and managing plugins dynamically.

This module provides a generic PluginManager class that can be used across
different frameworks (Flask, Django, etc.) to load and manage plugins with
consistent behavior.
"""

import importlib
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any


class PluginManager:
    """Generic plugin manager for loading and managing application plugins.

    This class provides framework-agnostic plugin loading with support for:
    - Dynamic plugin discovery from directories
    - Metadata validation
    - Optional singleton pattern
    - Framework-specific registration callbacks
    - Compiled (.so) and Python module support
    """

    _instance = None
    _use_singleton = True

    def __init__(
        self,
        plugins_dir: Path | str,
        plugins_pkg: str,
        logger: logging.Logger | None = None,
        use_singleton: bool = True,
        registration_callback: Callable[[dict[str, Any]], None] | None = None,
        plugin_submodule: str | None = None,
    ):
        """Initialize the PluginManager.

        Args:
            plugins_dir: Directory containing plugins
            plugins_pkg: Python package path for plugins (e.g., 'myapp.plugins')
            logger: Logger instance for logging (defaults to module logger)
            use_singleton: Whether to use singleton pattern (default: True)
            registration_callback: Optional callback for framework-specific registration
                                 (e.g., Flask blueprint registration, Django URL patterns)
            plugin_submodule: Submodule path within each plugin (e.g., 'src').
                            Set to None to import plugin directory directly.
                            Default: None (imports from plugin root).
        """
        self.plugins_dir = (
            Path(plugins_dir) if isinstance(plugins_dir, str) else plugins_dir
        )
        self.plugins_pkg = plugins_pkg
        self.logger = logger or logging.getLogger(__name__)
        self.plugins: dict[str, dict[str, Any]] = {}
        self.registration_callback = registration_callback
        self._use_singleton = use_singleton
        self.plugin_submodule = plugin_submodule

    def __new__(cls, *args, **kwargs):
        """Create singleton instance if use_singleton is True."""
        use_singleton = kwargs.get("use_singleton", True)

        if use_singleton:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
        else:
            # Create new instance if singleton is disabled
            return super().__new__(cls)

    def load_plugins(self) -> None:
        """Load plugins found in the plugins directory.

        Scans the plugins directory for valid plugin packages, validates their
        metadata, and optionally calls registration callback for framework-specific
        integration (e.g., Flask blueprints, Django URL patterns).
        """
        if not self.plugins_dir or not self.plugins_dir.exists():
            self.logger.warning(
                f"Plugins directory not found: {self.plugins_dir}. Skipping plugin loading."
            )
            return

        self.logger.info(f"Loading plugins from: {self.plugins_dir}")

        for item in os.listdir(os.fspath(self.plugins_dir)):
            # Skip __pycache__ and __init__.py
            if item.startswith("__"):
                continue

            pkg_name = item

            # Handle .so files (compiled Python extensions)
            if item.endswith(".so"):
                pkg_name = item.split(".")[0]
            # Skip non-directories and non-.so files
            elif not os.path.isdir(os.path.join(self.plugins_dir, item)):
                continue

            # Build import path with optional submodule
            if self.plugin_submodule:
                pkg_anchor = f"{self.plugins_pkg}.{pkg_name}.{self.plugin_submodule}"
            else:
                pkg_anchor = f"{self.plugins_pkg}.{pkg_name}"

            # Try to import the plugin module
            try:
                module = importlib.import_module(pkg_anchor)
            except ImportError as e:
                self.logger.error(f"Failed to load plugin ({pkg_name}): {str(e)}")
                continue

            # Validate plugin metadata
            metadata = getattr(module, "metadata", None)
            if not metadata:
                self.logger.warning(f"Skipping plugin ({pkg_name}): No metadata found.")
                continue

            # Skip disabled plugins
            if metadata.get("disable", False) or not metadata.get("is_active", True):
                self.logger.info(
                    f"Skipping disabled plugin: {pkg_name} "
                    f"v{metadata.get('version', 'unknown')}"
                )
                continue

            # Register plugin
            try:
                plugin_name = metadata["name"]
                plugin_data = {
                    "version": metadata.get("version", "unknown"),
                    "module": module,
                    "metadata": metadata,
                }

                # Add optional fields if present
                if "entrypoint_cls" in metadata:
                    plugin_data["entrypoint_cls"] = metadata["entrypoint_cls"]
                if "exception_cls" in metadata:
                    plugin_data["exception_cls"] = metadata["exception_cls"]
                if "service_class" in metadata:
                    plugin_data["service_class"] = metadata["service_class"]

                self.plugins[plugin_name] = plugin_data

                # Call framework-specific registration callback if provided
                if self.registration_callback:
                    self.registration_callback(plugin_data)

                self.logger.info(f"✔ Loaded plugin: {pkg_name} v{plugin_data['version']}")

            except KeyError as e:
                self.logger.error(f"Invalid metadata for plugin '{pkg_name}': {str(e)}")

        # Log appropriate message based on whether plugins were loaded
        if not self.plugins:
            self.logger.info("No plugins loaded (OSS mode).")

    def get_plugin(self, name: str) -> dict[str, Any]:
        """Get plugin metadata by name.

        Args:
            name: Plugin name to retrieve

        Returns:
            Dictionary containing plugin metadata (version, module, entrypoint_cls, etc.)
            or empty dict if plugin not found
        """
        return self.plugins.get(name, {})

    def has_plugin(self, name: str) -> bool:
        """Check if a plugin is loaded.

        Args:
            name: Plugin name to check

        Returns:
            bool: True if plugin is loaded, False otherwise
        """
        return name in self.plugins

    def get_all_plugins(self) -> dict[str, dict[str, Any]]:
        """Get all loaded plugins.

        Returns:
            Dictionary mapping plugin names to their metadata
        """
        return self.plugins.copy()

    def reload_plugins(self) -> None:
        """Reload all plugins from the plugins directory.

        Clears existing plugins and reloads them from disk.
        """
        self.plugins.clear()
        self.load_plugins()
