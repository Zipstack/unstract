import importlib
import os
from pathlib import Path
from typing import Any

from flask import Flask


class PluginManager:
    _instance = None

    def __new__(cls, app: Flask | None = None) -> "PluginManager":
        if cls._instance is None:
            # Only create the instance if it doesn't already exist
            cls._instance = super().__new__(cls)
            cls._instance.plugins = {}
            cls._instance.plugins_dir = Path(__file__).parent.parent / "plugins"
            cls._instance.plugins_pkg = "unstract.prompt_service.plugins"
        # Always update `app` if provided
        if app:
            cls._instance.app = app
        return cls._instance

    def load_plugins(self) -> None:
        """Loads plugins found in the plugins root dir."""
        if not self.plugins_dir.exists():
            self.app.logger.warning(
                f"Plugins directory not found: {self.plugins_dir}. Skipping."
            )
            return

        self.app.logger.info(f"Loading plugins from: {self.plugins_dir}")

        for pkg in os.listdir(os.fspath(self.plugins_dir)):
            if pkg.endswith(".so"):
                pkg = pkg.split(".")[0]
            pkg_anchor = f"{self.plugins_pkg}.{pkg}.src"
            try:
                module = importlib.import_module(pkg_anchor)
            except ImportError as e:
                self.app.logger.error(f"Failed to load plugin ({pkg}): {str(e)}")
                continue

            metadata = getattr(module, "metadata", None)
            if not metadata:
                self.app.logger.warning(f"Skipping plugin ({pkg}): No metadata found.")
                continue

            if metadata.get("disable", False):
                self.app.logger.info(
                    f"Skipping disabled plugin: {pkg}"
                    f" v{metadata.get('version', 'unknown')}"
                )
                continue

            try:
                self.plugins[metadata["name"]] = {
                    "version": metadata["version"],
                    "entrypoint_cls": metadata["entrypoint_cls"],
                    "exception_cls": metadata["exception_cls"],
                }
                if blueprint := metadata.get("blueprint"):
                    self.app.register_blueprint(blueprint)
                self.app.logger.info(f"✔ Loaded plugin: {pkg} v{metadata['version']}")
            except KeyError as e:
                self.app.logger.error(f"Invalid metadata for plugin '{pkg}': {str(e)}")

        if not self.plugins:
            self.app.logger.warning("⚠ No plugins loaded.")

    def get_plugin(self, name: str) -> dict[str, Any]:
        """Get the plugin metadata by name."""
        return self.plugins.get(name, {})


def plugin_loader(app: Flask) -> None:
    manager = PluginManager(app)
    manager.load_plugins()
