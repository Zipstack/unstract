import importlib
import os
from pathlib import Path
from typing import Any

from flask import Flask
from unstract.prompt_service_v2.constants import PromptServiceContants as PSKeys


class PluginManager:
    _instance = None

    def __new__(cls, app: Flask = None) -> "PluginManager":
        if cls._instance is None:
            # Only create the instance if it doesn't already exist
            cls._instance = super().__new__(cls)
            cls._instance.plugins = {}
            cls._instance.plugins_dir = (
                Path(
                    # Temporary change for v2 and will be removed once tested
                    os.path.dirname(__file__).replace(
                        "prompt_service_v2", "prompt_service"
                    )
                ).parent
                / "plugins"
            )
            cls._instance.plugins_pkg = "unstract.prompt_service.plugins"
            # Always update `app` if provided
            if app:
                cls._instance.app = app
        return cls._instance

    def load_plugins(self) -> None:
        """Loads plugins found in the plugins root dir."""
        if not self.plugins_dir.exists():
            self.app.logger.info(
                f"Plugins dir not found: {self.plugins_dir}. Skipping."
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

            if not hasattr(module, "metadata"):
                self.app.logger.warning(f"Plugin metadata not found: {pkg}")
                continue

            metadata: dict[str, Any] = module.metadata
            if metadata.get("disable", False):
                self.app.logger.info(
                    f"Ignore disabled plugin: {pkg} v{metadata['version']}"
                )
                continue

            try:
                self.plugins[metadata["name"]] = {
                    "version": metadata["version"],
                    "entrypoint_cls": metadata["entrypoint_cls"],
                    "exception_cls": metadata["exception_cls"],
                }
                self.app.logger.info(f"Loaded plugin: {pkg} v{metadata['version']}")
            except KeyError as e:
                self.app.logger.error(f"Invalid metadata for plugin '{pkg}': {str(e)}")

        if not self.plugins:
            self.app.logger.info("No plugins found.")

    def get_plugin(self, name: str) -> dict[str, Any]:
        """Get the plugin metadata by name."""
        return self.plugins.get(name, {})

    def initialize_plugin_endpoints(self) -> None:
        """Enables plugins if available."""
        single_pass_extration_plugin = self.get_plugin(PSKeys.SINGLE_PASS_EXTRACTION)
        summarize_plugin = self.get_plugin(PSKeys.SUMMARIZE)
        simple_prompt_studio = self.get_plugin(PSKeys.SIMPLE_PROMPT_STUDIO)

        if single_pass_extration_plugin:
            single_pass_extration_plugin["entrypoint_cls"](
                app=self.app,
                challenge_plugin=self.get_plugin(PSKeys.CHALLENGE),
                get_cleaned_context=self.get_cleaned_context,
                highlight_data_plugin=self.get_plugin(PSKeys.HIGHLIGHT_DATA_PLUGIN),
            )
        if summarize_plugin:
            summarize_plugin["entrypoint_cls"](app=self.app)
        if simple_prompt_studio:
            simple_prompt_studio["entrypoint_cls"](app=self.app)

    def get_cleaned_context(self, context: set[str]) -> list[str]:
        """Returns cleaned context from the clean context plugin."""
        clean_context_plugin = self.get_plugin(PSKeys.CLEAN_CONTEXT)
        if clean_context_plugin:
            return clean_context_plugin["entrypoint_cls"].run(context=context)
        return list(context)


def plugin_loader(app: Flask) -> None:
    manager = PluginManager(app)
    manager.load_plugins()
    manager.initialize_plugin_endpoints()
