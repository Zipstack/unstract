import logging
import os
from importlib import import_module
from typing import Any

from django.apps import apps

logger = logging.getLogger(__name__)


class ModifierConfig:
    """Loader config for extraction plugins."""

    PLUGINS_APP = "plugins"
    PLUGIN_DIR = "modifier"
    MODULE = "module"
    METADATA = "metadata"
    METADATA_NAME = "name"
    METADATA_SERVICE_CLASS = "service_class"
    METADATA_IS_ACTIVE = "is_active"


# Cache for loaded plugins to avoid repeated loading
_modifier_plugins_cache: list[Any] = []
_plugins_loaded = False


def load_plugins() -> list[Any]:
    """Iterate through the extraction plugins and register them."""
    global _modifier_plugins_cache, _plugins_loaded

    # Return cached plugins if already loaded
    if _plugins_loaded:
        return _modifier_plugins_cache

    plugins_app = apps.get_app_config(ModifierConfig.PLUGINS_APP)
    package_path = plugins_app.module.__package__
    modifier_dir = os.path.join(plugins_app.path, ModifierConfig.PLUGIN_DIR)
    modifier_package_path = f"{package_path}.{ModifierConfig.PLUGIN_DIR}"
    modifier_plugins: list[Any] = []

    if not os.path.exists(modifier_dir):
        _modifier_plugins_cache = modifier_plugins
        _plugins_loaded = True
        return modifier_plugins

    for item in os.listdir(modifier_dir):
        # Loads a plugin if it is in a directory.
        if os.path.isdir(os.path.join(modifier_dir, item)):
            modifier_module_name = item
        # Loads a plugin if it is a shared library.
        # Module name is extracted from shared library name.
        elif item.endswith(".so"):
            modifier_module_name = item.split(".")[0]
        else:
            continue
        try:
            full_module_path = f"{modifier_package_path}.{modifier_module_name}"
            module = import_module(full_module_path)
            metadata = getattr(module, ModifierConfig.METADATA, {})

            if metadata.get(ModifierConfig.METADATA_IS_ACTIVE, False):
                modifier_plugins.append(
                    {
                        ModifierConfig.MODULE: module,
                        ModifierConfig.METADATA: module.metadata,
                    }
                )
                logger.info(
                    "Loaded modifier plugin: %s, is_active: %s",
                    module.metadata[ModifierConfig.METADATA_NAME],
                    module.metadata[ModifierConfig.METADATA_IS_ACTIVE],
                )
            else:
                logger.info(
                    "modifier plugin %s is not active.",
                    modifier_module_name,
                )
        except ModuleNotFoundError:
            logger.warning("No prompt modifier plugins loaded")

    if len(modifier_plugins) == 0:
        logger.info("No modifier plugins found.")

    # Cache the results for future requests
    _modifier_plugins_cache = modifier_plugins
    _plugins_loaded = True

    return modifier_plugins
