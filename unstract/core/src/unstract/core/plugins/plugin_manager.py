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
        self.logger.info("=" * 80)
        self.logger.info("PLUGIN LOADING STARTED")
        self.logger.info("=" * 80)

        # Step 1: Validate plugins directory
        if not self.plugins_dir:
            self.logger.error(
                "❌ FATAL: plugins_dir is None or empty. Cannot load plugins."
            )
            return

        self.logger.info(f"📁 Plugins directory configured: {self.plugins_dir}")
        self.logger.info(f"📦 Plugins package: {self.plugins_pkg}")
        self.logger.info(f"🔧 Plugin submodule: {self.plugin_submodule or 'None (root)'}")

        if not self.plugins_dir.exists():
            self.logger.error(
                f"❌ FATAL: Plugins directory does not exist: {self.plugins_dir}"
            )
            self.logger.error(f"   Absolute path: {self.plugins_dir.absolute()}")
            self.logger.error("   Skipping plugin loading.")
            return

        self.logger.info(f"✓ Plugins directory exists: {self.plugins_dir.absolute()}")

        # List directory contents for debugging
        try:
            dir_contents = list(self.plugins_dir.iterdir())
            self.logger.info(f"📂 Directory contains {len(dir_contents)} items:")
            for item in sorted(dir_contents):
                item_type = "DIR" if item.is_dir() else "FILE"
                self.logger.info(f"   [{item_type}] {item.name}")
        except Exception as e:
            self.logger.error(f"❌ ERROR: Cannot list directory contents: {e}")
            return

        # Step 2: Discover plugin candidates
        self.logger.info("-" * 80)
        self.logger.info("DISCOVERING PLUGIN CANDIDATES")
        self.logger.info("-" * 80)

        plugin_candidates = self._find_plugin_modules(self.plugins_dir, max_depth=2)

        if not plugin_candidates:
            self.logger.warning(
                "⚠ No plugin candidates found in directory. "
                "Looking for directories with __init__.py"
            )
            self.logger.info("No plugins loaded (OSS mode).")
            return

        self.logger.info(f"✓ Found {len(plugin_candidates)} plugin candidate(s):")
        for idx, (plugin_path, module_name) in enumerate(plugin_candidates, 1):
            self.logger.info(f"   {idx}. {module_name} → {plugin_path}")

        # Step 3: Load each plugin
        self.logger.info("-" * 80)
        self.logger.info("LOADING PLUGINS")
        self.logger.info("-" * 80)

        loaded_count = 0
        skipped_count = 0
        failed_count = 0

        for idx, (plugin_path, module_name) in enumerate(plugin_candidates, 1):
            self.logger.info(f"\n[{idx}/{len(plugin_candidates)}] Processing: {module_name}")
            self.logger.info(f"   Path: {plugin_path}")

            # Build import path with optional submodule
            if self.plugin_submodule:
                pkg_anchor = f"{self.plugins_pkg}.{module_name}.{self.plugin_submodule}"
            else:
                pkg_anchor = f"{self.plugins_pkg}.{module_name}"

            self.logger.info(f"   Import path: {pkg_anchor}")

            # Try to import the plugin module
            try:
                self.logger.debug(f"   Attempting to import: {pkg_anchor}")
                
                module = importlib.import_module("unstract.prompt_service.plugins.agentic_extraction")
                self.logger.debug(f"   ✓ Import successful")
            except ImportError as e:
                self.logger.warning(
                    f"   ⚠ Import failed for {pkg_anchor}: {str(e)}"
                )
                self.logger.debug(f"   Full error: {repr(e)}", exc_info=True)
                failed_count += 1
                continue
            except Exception as e:
                self.logger.error(
                    f"   ❌ Unexpected error importing {pkg_anchor}: {str(e)}"
                )
                self.logger.error(f"   Error type: {type(e).__name__}")
                self.logger.debug(f"   Full traceback:", exc_info=True)
                failed_count += 1
                continue

            # Validate plugin metadata
            self.logger.debug(f"   Checking for 'metadata' attribute...")
            metadata = getattr(module, "metadata", None)

            if not metadata:
                self.logger.debug(
                    f"   ⚠ No 'metadata' found in {pkg_anchor} - not a plugin"
                )
                skipped_count += 1
                continue

            self.logger.info(f"   ✓ Metadata found:")
            self.logger.info(f"      - name: {metadata.get('name', 'MISSING')}")
            self.logger.info(f"      - version: {metadata.get('version', 'MISSING')}")
            self.logger.info(f"      - disable: {metadata.get('disable', False)}")
            self.logger.info(f"      - is_active: {metadata.get('is_active', True)}")

            # Check for required metadata keys
            required_keys = ['name', 'version']
            missing_keys = [key for key in required_keys if key not in metadata]
            if missing_keys:
                self.logger.error(
                    f"   ❌ Invalid metadata: missing required keys: {missing_keys}"
                )
                failed_count += 1
                continue

            # Skip disabled plugins
            if metadata.get("disable", False) or not metadata.get("is_active", True):
                self.logger.info(
                    f"   ⊗ Skipping disabled plugin: {metadata['name']} "
                    f"v{metadata.get('version', 'unknown')}"
                )
                skipped_count += 1
                continue

            # Register plugin
            try:
                plugin_name = metadata["name"]

                self.logger.debug(f"   Building plugin data structure...")
                plugin_data = {
                    "version": metadata.get("version", "unknown"),
                    "module": module,
                    "metadata": metadata,
                }

                # Add optional fields if present
                optional_fields = ["entrypoint_cls", "exception_cls", "service_class", "blueprint"]
                for field in optional_fields:
                    if field in metadata:
                        plugin_data[field] = metadata[field]
                        self.logger.debug(f"      - Added {field}: {metadata[field]}")

                self.plugins[plugin_name] = plugin_data
                self.logger.debug(f"   ✓ Plugin registered in plugins dict")

                # Call framework-specific registration callback if provided
                if self.registration_callback:
                    self.logger.debug(f"   Calling registration callback...")
                    try:
                        self.registration_callback(plugin_data)
                        self.logger.debug(f"   ✓ Registration callback completed")
                    except Exception as e:
                        self.logger.error(
                            f"   ❌ Registration callback failed: {str(e)}"
                        )
                        self.logger.error(f"   Error type: {type(e).__name__}")
                        self.logger.debug("   Full traceback:", exc_info=True)
                        # Remove from plugins dict if callback failed
                        del self.plugins[plugin_name]
                        failed_count += 1
                        continue

                loaded_count += 1
                self.logger.info(
                    f"   ✔ Successfully loaded plugin: {plugin_name} v{plugin_data['version']}"
                )

            except KeyError as e:
                self.logger.error(
                    f"   ❌ Invalid metadata for plugin '{module_name}': missing key {str(e)}"
                )
                self.logger.debug("   Full traceback:", exc_info=True)
                failed_count += 1
            except Exception as e:
                self.logger.error(
                    f"   ❌ Unexpected error registering plugin '{module_name}': {str(e)}"
                )
                self.logger.error(f"   Error type: {type(e).__name__}")
                self.logger.debug("   Full traceback:", exc_info=True)
                failed_count += 1

        # Final summary
        self.logger.info("=" * 80)
        self.logger.info("PLUGIN LOADING SUMMARY")
        self.logger.info("=" * 80)
        self.logger.info(f"✔ Successfully loaded: {loaded_count}")
        self.logger.info(f"⊗ Skipped (disabled): {skipped_count}")
        self.logger.info(f"❌ Failed to load: {failed_count}")
        self.logger.info(f"📊 Total candidates: {len(plugin_candidates)}")

        if self.plugins:
            self.logger.info(f"\n🎉 Active plugins ({len(self.plugins)}):")
            for name, data in self.plugins.items():
                self.logger.info(f"   • {name} v{data['version']}")
        else:
            self.logger.info("\nNo plugins loaded (OSS mode).")

        self.logger.info("=" * 80)

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
