"""Flask-specific plugin manager wrapper.

This module provides Flask integration for the generic PluginManager,
handling Flask-specific features like blueprint registration and app.logger
integration.
"""

from pathlib import Path
from typing import Any

from flask import Flask

from unstract.core.plugins import PluginManager as GenericPluginManager


class FlaskPluginManager:
    """Flask-specific plugin manager wrapper.

    Wraps the generic PluginManager with Flask-specific functionality like
    blueprint registration and Flask app integration.
    """

    _instance = None

    def __new__(
        cls,
        app: Flask | None = None,
        plugins_dir: Path | None = None,
        plugins_pkg: str | None = None,
    ) -> "FlaskPluginManager":
        """Create or return the singleton FlaskPluginManager instance.

        Args:
            app: Flask application instance
            plugins_dir: Directory containing plugins
            plugins_pkg: Python package path for plugins

        Returns:
            FlaskPluginManager singleton instance
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False

        # Update app if provided
        if app:
            cls._instance.app = app

        # Initialize or update plugin manager if parameters change
        if plugins_dir and plugins_pkg and hasattr(cls._instance, "app"):
            if (
                not cls._instance._initialized
                or cls._instance._plugins_dir != plugins_dir
                or cls._instance._plugins_pkg != plugins_pkg
            ):
                cls._instance._plugins_dir = plugins_dir
                cls._instance._plugins_pkg = plugins_pkg
                cls._instance._init_manager()

        return cls._instance

    def _init_manager(self) -> None:
        """Initialize the generic plugin manager with Flask-specific callback."""

        def flask_registration_callback(plugin_data: dict[str, Any]) -> None:
            """Flask-specific registration callback for blueprints."""
            metadata = plugin_data.get("metadata", {})
            if blueprint := metadata.get("blueprint"):
                self.app.register_blueprint(blueprint)
                self.app.logger.debug(
                    f"Registered blueprint for plugin: {metadata.get('name', 'unknown')}"
                )

        self._manager = GenericPluginManager(
            plugins_dir=self._plugins_dir,
            plugins_pkg=self._plugins_pkg,
            logger=self.app.logger,
            use_singleton=True,
            registration_callback=flask_registration_callback,
        )
        self._initialized = True

    def load_plugins(self) -> None:
        """Load plugins using the generic manager."""
        if not self._initialized:
            raise RuntimeError(
                "FlaskPluginManager not initialized. "
                "Call with app, plugins_dir, and plugins_pkg first."
            )
        self._manager.load_plugins()

    def get_plugin(self, name: str) -> dict[str, Any]:
        """Get plugin metadata by name.

        Args:
            name: Plugin name to retrieve

        Returns:
            Dictionary containing plugin metadata
        """
        if not self._initialized:
            return {}
        return self._manager.get_plugin(name)

    def has_plugin(self, name: str) -> bool:
        """Check if a plugin is loaded.

        Args:
            name: Plugin name to check

        Returns:
            bool: True if plugin exists
        """
        if not self._initialized:
            return False
        return self._manager.has_plugin(name)

    @property
    def plugins(self) -> dict[str, dict[str, Any]]:
        """Get all loaded plugins."""
        if not self._initialized:
            return {}
        return self._manager.get_all_plugins()


# Maintain backward compatibility with old class name
PluginManager = FlaskPluginManager


def plugin_loader(
    app: Flask,
    plugins_dir: Path | None = None,
    plugins_pkg: str | None = None,
) -> None:
    """Load plugins for a Flask application.

    Convenience function to create a PluginManager instance and load plugins.

    Args:
        app: Flask application instance
        plugins_dir: Directory containing plugins (optional, defaults to auto-detection)
        plugins_pkg: Python package path for plugins (optional)

    Example:
        # In your Flask app configuration:
        from unstract.core.flask import plugin_loader

        def create_app():
            app = Flask(__name__)
            plugin_loader(app)  # Auto-detects plugin location
            return app
    """
    manager = PluginManager(app, plugins_dir, plugins_pkg)
    manager.load_plugins()
