import logging
import os
from importlib import import_module
from typing import Any

from account.constants import PluginConfig
from django.apps import apps

Logger = logging.getLogger(__name__)


def _load_plugins() -> dict[str, dict[str, Any]]:
    """Iterating through the Authentication plugins and register their
    metadata."""
    auth_app = apps.get_app_config(PluginConfig.PLUGINS_APP)
    auth_package_path = auth_app.module.__package__
    auth_dir = os.path.join(auth_app.path, PluginConfig.AUTH_PLUGIN_DIR)
    auth_package_path = f"{auth_package_path}.{PluginConfig.AUTH_PLUGIN_DIR}"
    auth_modules = {}

    for item in os.listdir(auth_dir):
        # Loads a plugin only if name starts with `auth`.
        if not item.startswith(PluginConfig.AUTH_MODULE_PREFIX):
            continue
        # Loads a plugin if it is in a directory.
        if os.path.isdir(os.path.join(auth_dir, item)):
            auth_module_name = item
        # Loads a plugin if it is a shared library.
        # Module name is extracted from shared library name.
        # `auth.platform_architecture.so` will be file name and
        # `auth` will be the module name.
        elif item.endswith(".so"):
            auth_module_name = item.split(".")[0]
        else:
            continue
        try:
            full_module_path = f"{auth_package_path}.{auth_module_name}"
            module = import_module(full_module_path)
            metadata = getattr(module, PluginConfig.AUTH_METADATA, {})
            if metadata.get(PluginConfig.METADATA_IS_ACTIVE, False):
                auth_modules[auth_module_name] = {
                    PluginConfig.AUTH_MODULE: module,
                    PluginConfig.AUTH_METADATA: module.metadata,
                }
                Logger.info(
                    "Loaded active authentication plugin: %s", module.metadata["name"]
                )
            else:
                Logger.info(
                    "Skipping inactive authentication plugin: %s", auth_module_name
                )
        except ModuleNotFoundError as exception:
            Logger.error(
                "Error while importing authentication module : %s",
                exception,
            )

    if len(auth_modules) > 1:
        raise ValueError(
            "Multiple authentication modules found."
            "Only one authentication method is allowed."
        )
    elif len(auth_modules) == 0:
        Logger.warning(
            "No authentication modules found."
            "Application will start without authentication module"
        )
    return auth_modules


class AuthenticationPluginRegistry:
    auth_modules: dict[str, dict[str, Any]] = _load_plugins()

    @classmethod
    def is_plugin_available(cls) -> bool:
        """Check if any authentication plugin is available.

        Returns:
            bool: True if a plugin is available, False otherwise.
        """
        return len(cls.auth_modules) > 0

    @classmethod
    def get_plugin(cls) -> Any:
        """Get the selected authentication plugin.

        Returns:
            AuthenticationService: Selected authentication plugin instance.
        """
        chosen_auth_module = next(iter(cls.auth_modules.values()))
        chosen_metadata = chosen_auth_module[PluginConfig.AUTH_METADATA]
        service_class_name = chosen_metadata[PluginConfig.METADATA_SERVICE_CLASS]
        return service_class_name()
