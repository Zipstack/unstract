import logging
import warnings
from os import environ as env
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from unstract.core.flask import (
    PluginManager,
    register_error_handlers,
    register_request_id_middleware,
)
from unstract.core.flask.logging import setup_logging
from unstract.prompt_service.controllers import api
from unstract.sdk1.constants import LogLevel

load_dotenv()


def create_app() -> Flask:
    """Creates and configures the Flask application."""
    log_level = env.get("LOG_LEVEL", LogLevel.INFO.value).upper()
    setup_logging(log_level)

    # Suppress OpenTelemetry EventLogger LogRecord deprecation warning
    # This is a bug in OpenTelemetry SDK 1.37.0 where EventLogger.emit() still uses
    # deprecated trace_id/span_id/trace_flags parameters instead of context parameter.
    # See: https://github.com/open-telemetry/opentelemetry-python/issues/4328
    # TODO: Remove this suppression once OpenTelemetry fixes EventLogger.emit()
    warnings.filterwarnings(
        "ignore",
        message="LogRecord init with.*trace_id.*span_id.*trace_flags.*deprecated",
        category=DeprecationWarning,
        module="opentelemetry.sdk._events",
    )

    log_level = getattr(logging, log_level, logging.INFO)
    app = Flask("prompt-service")
    app.logger.setLevel(log_level)
    app.logger.info("Initializing Flask application...")

    # Load plugins
    plugins_dir = Path(__file__).parent / "plugins"
    plugins_pkg = "unstract.prompt_service.plugins"
    manager = PluginManager(app, plugins_dir, plugins_pkg)
    manager.load_plugins()

    register_request_id_middleware(app)
    register_error_handlers(app)
    app.register_blueprint(api)

    app.logger.info("Flask app created successfully.")
    return app
