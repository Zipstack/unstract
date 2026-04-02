"""Django AppConfig for backend plugins."""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class PluginsConfig(AppConfig):
    """Django AppConfig for the plugins package.

    This loads plugins after Django is fully initialized to avoid
    AppRegistryNotReady errors.
    """

    name = "plugins"
    verbose_name = "Backend Plugins"

    def ready(self) -> None:
        """Load plugins after Django apps are ready.

        This method is called by Django after all apps are loaded,
        ensuring that models and other Django components are available.
        """
        from plugins import get_plugin_manager

        try:
            plugin_manager = get_plugin_manager()
            plugin_manager.load_plugins()
            logger.info("Backend plugins loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load plugins: {e}", exc_info=True)
            # Don't raise - allow Django to continue even if plugins fail
