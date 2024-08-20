import logging
import os
from importlib import import_module
from typing import Any

from django.apps import apps

logger = logging.getLogger(__name__)


class ProcessorConfig:
    """Loader config for processor plugins."""

    PLUGINS_APP = "plugins"
    PLUGIN_DIR = "processor"
    MODULE = "module"
    METADATA = "metadata"
    METADATA_NAME = "name"
    METADATA_SERVICE_CLASS = "service_class"
    METADATA_IS_ACTIVE = "is_active"


def load_plugins() -> list[Any]:
    """Iterate through the processor plugins and register them."""
    plugins_app = apps.get_app_config(ProcessorConfig.PLUGINS_APP)
    package_path = plugins_app.module.__package__
    processor_dir = os.path.join(plugins_app.path, ProcessorConfig.PLUGIN_DIR)
    processor_package_path = f"{package_path}.{ProcessorConfig.PLUGIN_DIR}"
    processor_plugins: list[Any] = []

    for item in os.listdir(processor_dir):
        # Loads a plugin if it is in a directory.
        if os.path.isdir(os.path.join(processor_dir, item)):
            processor_module_name = item
        # Loads a plugin if it is a shared library.
        # Module name is extracted from shared library name.
        # `processor.platform_architecture.so` will be file name and
        # `processor` will be the module name.
        elif item.endswith(".so"):
            processor_module_name = item.split(".")[0]
        else:
            continue
        try:
            full_module_path = f"{processor_package_path}.{processor_module_name}"
            module = import_module(full_module_path)
            metadata = getattr(module, ProcessorConfig.METADATA, {})

            if metadata.get(ProcessorConfig.METADATA_IS_ACTIVE, False):
                processor_plugins.append(
                    {
                        ProcessorConfig.MODULE: module,
                        ProcessorConfig.METADATA: module.metadata,
                    }
                )
                logger.info(
                    "Loaded processor plugin: %s, is_active: %s",
                    module.metadata[ProcessorConfig.METADATA_NAME],
                    module.metadata[ProcessorConfig.METADATA_IS_ACTIVE],
                )
            else:
                logger.info(
                    "Processor plugin %s is not active.",
                    processor_module_name,
                )
        except ModuleNotFoundError as exception:
            logger.error(
                "Error while importing processor plugin: %s",
                exception,
            )

    if len(processor_plugins) == 0:
        logger.info("No processor plugins found.")

    return processor_plugins


def get_plugin_class_by_name(name: str, plugins: list[Any]) -> Any:
    """Retrieve a specific plugin class by name."""
    for plugin in plugins:
        metadata = plugin[ProcessorConfig.METADATA]
        if metadata.get(ProcessorConfig.METADATA_NAME) == name:
            return metadata.get(ProcessorConfig.METADATA_SERVICE_CLASS)
    logger.warning("Plugin with name '%s' not found.", name)
    return None
