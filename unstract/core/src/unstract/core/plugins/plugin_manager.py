"""Framework-agnostic plugin manager for loading and managing plugins dynamically.

This module provides a generic PluginManager class that can be used across
different frameworks (Flask, Django, etc.) to load and manage plugins with
consistent behavior.
"""

import importlib
import logging
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

    def _find_plugin_modules(
        self, base_path: Path, max_depth: int = 2
    ) -> list[tuple[Path, str]]:
        """Recursively find plugin directories containing valid metadata.

        Scans the plugin directory tree up to max_depth levels to find directories
        with __init__.py that contain plugin metadata. This supports both flat
        plugin structures (plugins/plugin_name/) and nested structures
        (plugins/category/plugin_name/).

        Args:
            base_path: Root directory to start searching from
            max_depth: Maximum directory depth to search (default: 2)
                      depth=0: only base_path
                      depth=1: base_path + immediate subdirs
                      depth=2: base_path + subdirs + their subdirs

        Returns:
            List of tuples (plugin_path, module_name) where:
                - plugin_path: Path to the plugin directory
                - module_name: Dot-separated module path relative to plugins_pkg
                  (e.g., 'base_plugin.nested_plugin' or 'base_plugin')

        """
        plugins = []

        def _scan_directory(path: Path, depth: int = 0, rel_parts: tuple[str, ...] = ()):
            """Recursively scan directories for plugins.

            Args:
                path: Current directory being scanned
                depth: Current recursion depth
                rel_parts: Tuple of path components relative to base_path
            """
            if depth > max_depth:
                return

            try:
                items = sorted(path.iterdir())
            except OSError as e:
                self.logger.warning(
                    f"Cannot access directory {path} for plugin discovery: {e}"
                )
                return

            for item in items:
                # Skip special Python directories and build artifacts
                if item.name.startswith("__") or item.name in (
                    "build",
                    "dist",
                    "egg-info",
                    ".pytest_cache",
                    ".mypy_cache",
                    "node_modules",
                ):
                    continue

                # Handle .so files (compiled extensions) at any level
                if item.name.endswith(".so"):
                    pkg_name = item.name.split(".")[0]
                    module_path = ".".join(rel_parts + (pkg_name,))
                    plugins.append((item, module_path))
                    continue

                # Only process directories
                if not item.is_dir():
                    continue

                # Build relative module path
                new_rel_parts = rel_parts + (item.name,)

                # Check if this directory has __init__.py
                init_file = item / "__init__.py"
                if init_file.exists():
                    # This could be a plugin - add it to candidates
                    module_path = ".".join(new_rel_parts)
                    plugins.append((item, module_path))

                # Continue scanning subdirectories if we haven't reached max depth
                if depth < max_depth:
                    _scan_directory(item, depth + 1, new_rel_parts)

        _scan_directory(base_path)
        return plugins

    def load_plugins(self) -> None:
        """Load plugins found in the plugins directory.

        Scans the plugins directory recursively for valid plugin packages,
        validates their metadata, and optionally calls registration callback
        for framework-specific integration (e.g., Flask blueprints, Django URL patterns).

        Supports both flat plugin structures (plugins/plugin_name/) and nested
        structures (plugins/category/plugin_name/) up to max_depth levels.
        """
        if not self.plugins_dir or not self.plugins_dir.exists():
            self.logger.warning(
                f"Plugins directory not found: {self.plugins_dir}. Skipping plugin loading."
            )
            return

        self.logger.info(f"Loading plugins from: {self.plugins_dir}")

        # Recursively discover all potential plugin directories
        plugin_candidates = self._find_plugin_modules(self.plugins_dir, max_depth=2)

        for plugin_path, module_name in plugin_candidates:
            # Build import path with optional submodule
            if self.plugin_submodule:
                pkg_anchor = f"{self.plugins_pkg}.{module_name}.{self.plugin_submodule}"
            else:
                pkg_anchor = f"{self.plugins_pkg}.{module_name}"

            # Try to import the plugin module
            try:
                module = importlib.import_module(pkg_anchor)
            except ImportError as e:
                self.logger.debug(
                    f"Could not import {pkg_anchor} (might not be a plugin): {str(e)}"
                )
                continue

            # Validate plugin metadata
            metadata = getattr(module, "metadata", None)
            if not metadata:
                # Not a plugin - just a regular directory with __init__.py
                continue

            # Skip disabled plugins
            if metadata.get("disable", False) or not metadata.get("is_active", True):
                self.logger.info(
                    f"Skipping disabled plugin: {module_name} "
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

                self.logger.info(
                    f"✔ Loaded plugin: {plugin_name} v{plugin_data['version']}"
                )

            except KeyError as e:
                self.logger.error(
                    f"Invalid metadata for plugin '{module_name}': {str(e)}"
                )

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
