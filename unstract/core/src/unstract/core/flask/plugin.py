"""Flask-specific plugin manager wrapper.

This module provides Flask integration for the generic PluginManager,
handling Flask-specific features like blueprint registration and app.logger
integration.
"""

import threading
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
    _lock = threading.Lock()

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
        with cls._lock:
            # Check inside lock to handle race condition
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False

            # Update app if provided
            if app:
                cls._instance.app = app

            # Initialize or update plugin manager if parameters change
            if (
                plugins_dir
                and plugins_pkg
                and hasattr(cls._instance, "app")
                and (
                    not cls._instance._initialized
                    or cls._instance._plugins_dir != plugins_dir
                    or cls._instance._plugins_pkg != plugins_pkg
                )
            ):
                cls._instance._plugins_dir = plugins_dir
                cls._instance._plugins_pkg = plugins_pkg
                cls._instance._init_manager()

        return cls._instance

    def _init_manager(self) -> None:
        """Initialize the generic plugin manager with Flask-specific callback."""

       def flask_registration_callback(plugin_data: dict[str, Any]) -> None:
            """Flask-specific registration callback for blueprints with detailed logging."""
            plugin_name = plugin_data.get("metadata", {}).get("name", "unknown")
            plugin_version = plugin_data.get("version", "unknown")

            self.app.logger.debug(
                f"[BLUEPRINT] Processing plugin: {plugin_name} v{plugin_version}"
            )

            metadata = plugin_data.get("metadata", {})

            # Check if blueprint exists in metadata
            if "blueprint" not in metadata:
                self.app.logger.debug(
                    f"[BLUEPRINT] No blueprint found in plugin '{plugin_name}' metadata - skipping"
                )
                return

            blueprint = metadata.get("blueprint")

            # Validate blueprint object
            if blueprint is None:
                self.app.logger.warning(
                    f"[BLUEPRINT] ⚠ Plugin '{plugin_name}' has 'blueprint' key but value is None"
                )
                return

            if not hasattr(blueprint, "name"):
                self.app.logger.error(
                    f"[BLUEPRINT] ❌ Invalid blueprint object for plugin '{plugin_name}': "
                    f"missing 'name' attribute (type: {type(blueprint).__name__})"
                )
                return

            # Log blueprint details
            self.app.logger.info(
                f"[BLUEPRINT] Found blueprint in plugin '{plugin_name}':"
            )
            self.app.logger.info(f"[BLUEPRINT]   - Blueprint name: {blueprint.name}")
            self.app.logger.info(
                f"[BLUEPRINT]   - URL prefix: {blueprint.url_prefix or '(none)'}"
            )
            self.app.logger.info(
                f"[BLUEPRINT]   - Import name: {blueprint.import_name}"
            )

            # Check if already registered
            if blueprint.name in self.app.blueprints:
                self.app.logger.warning(
                    f"[BLUEPRINT] ⚠ Blueprint '{blueprint.name}' already registered, skipping"
                )
                existing_bp = self.app.blueprints[blueprint.name]
                self.app.logger.debug(
                    f"[BLUEPRINT]   Existing blueprint URL prefix: {existing_bp.url_prefix}"
                )
                return

            # Register blueprint
            try:
                self.app.logger.info(
                    f"[BLUEPRINT] Registering blueprint '{blueprint.name}'..."
                )
                self.app.register_blueprint(blueprint)

                # Verify registration
                if blueprint.name in self.app.blueprints:
                    self.app.logger.info(
                        f"[BLUEPRINT] ✔ Successfully registered blueprint '{blueprint.name}' "
                        f"for plugin '{plugin_name}'"
                    )

                    # Count and log routes
                    try:
                        route_count = sum(
                            1
                            for rule in self.app.url_map.iter_rules()
                            if rule.endpoint.startswith(f"{blueprint.name}.")
                        )
                        self.app.logger.info(
                            f"[BLUEPRINT]   - Registered {route_count} route(s)"
                        )

                        # Log sample routes (first 5)
                        if route_count > 0:
                            self.app.logger.debug(
                                f"[BLUEPRINT]   Sample routes for '{blueprint.name}':"
                            )
                            count = 0
                            for rule in self.app.url_map.iter_rules():
                                if rule.endpoint.startswith(f"{blueprint.name}."):
                                    methods = ",".join(
                                        sorted(rule.methods - {"HEAD", "OPTIONS"})
                                    )
                                    self.app.logger.debug(
                                        f"[BLUEPRINT]     [{methods:8s}] {rule.rule}"
                                    )
                                    count += 1
                                    if count >= 5:
                                        if route_count > 5:
                                            self.app.logger.debug(
                                                f"[BLUEPRINT]     ... and {route_count - 5} more"
                                            )
                                        break
                    except Exception as e:
                        self.app.logger.debug(
                            f"[BLUEPRINT]   Could not enumerate routes: {e}"
                        )

                else:
                    self.app.logger.error(
                        f"[BLUEPRINT] ❌ Blueprint '{blueprint.name}' not found in app.blueprints "
                        f"after registration (plugin: {plugin_name})"
                    )

            except Exception as e:
                self.app.logger.error(
                    f"[BLUEPRINT] ❌ Failed to register blueprint '{blueprint.name}' "
                    f"for plugin '{plugin_name}': {e}"
                )
                self.app.logger.error(f"[BLUEPRINT]   Error type: {type(e).__name__}")
                self.app.logger.debug(
                    f"[BLUEPRINT]   Full error details:", exc_info=True
                )
                raise  # Re-raise to be caught by plugin manager


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
        plugins_dir: Directory containing plugins (required)
        plugins_pkg: Python package path for plugins (required)

    Raises:
        ValueError: If plugins_dir or plugins_pkg is not provided

    Example:
        from pathlib import Path
        from unstract.core.flask import plugin_loader

        def create_app():
            app = Flask(__name__)
            plugins_dir = Path(__file__).parent / "plugins"
            plugin_loader(app, plugins_dir, "unstract.myservice.plugins")
            return app
    """
    if not plugins_dir or not plugins_pkg:
        raise ValueError(
            "Both 'plugins_dir' and 'plugins_pkg' are required for plugin_loader.\n\n"
            "Example usage:\n"
            "  from pathlib import Path\n"
            "  plugins_dir = Path(__file__).parent / 'plugins'\n"
            "  plugin_loader(app, plugins_dir, 'unstract.myservice.plugins')"
        )

    manager = PluginManager(app, plugins_dir, plugins_pkg)
    manager.load_plugins()
