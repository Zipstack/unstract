import importlib
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv
from flask import current_app
import redis

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
)


class EnvLoader:
    @staticmethod
    def get_env_or_die(env_key: str) -> str:
        env_value = os.environ.get(env_key)
        if env_value is None or env_value == "":
            logging.error(f"Env variable {env_key} is required")
            sys.exit(1)
        return env_value  # type:ignore


class PluginException(Exception):
    """All exceptions raised from a plugin."""


def plugin_loader() -> dict[str, dict[str, Any]]:
    """Loads plugins found in the plugins root dir.

    Each plugin:
    * needs to be a package dir AND
    * should contain a src/__init__.py which exports below:

        metadata: dict[str, Any] = {
            "version": str,
            "name": str,
            "entrypoint_cls": class,
            "exception_cls": class,
            "disable": bool
        }
    """
    plugins_dir: Path = Path(os.path.dirname(__file__)) / "plugins"
    plugins_pkg = "unstract.prompt_service.plugins"

    if not plugins_dir.exists():
        print(f"Plugins dir not found: {plugins_dir}. Skipping.")
        return {}

    plugins: dict[str, dict[str, Any]] = {}
    print(f"Loading plugins from: {plugins_dir}")

    for pkg in os.listdir(os.fspath(plugins_dir)):
        if pkg.endswith(".so"):
            pkg = pkg.split(".")[0]
        pkg_anchor = f"{plugins_pkg}.{pkg}.src"
        try:
            module = importlib.import_module(pkg_anchor)
        except ImportError as e:
            print(f"Failed to load plugin ({pkg}): {str(e)}")
            continue

        if not hasattr(module, "metadata"):
            print(f"Plugin metadata not found: {pkg}")
            continue

        metadata: dict[str, Any] = module.metadata
        if metadata.get("disable", False):
            print(f"Ignore disabled plugin: {pkg} v{metadata['version']}")
            continue

        try:
            plugins[metadata["name"]] = {
                "version": metadata["version"],
                "entrypoint_cls": metadata["entrypoint_cls"],
                "exception_cls": metadata["exception_cls"],
            }
            print(f"Loaded plugin: {pkg} v{metadata['version']}")
        except KeyError as e:
            print(f"Invalid metadata for plugin '{pkg}': {str(e)}")

    if not plugins:
        print("No plugins found.")

    return plugins
