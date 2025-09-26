import logging
from os import environ as env

from dotenv import load_dotenv
from flask import Flask

from unstract.core.flask import register_error_handlers, register_request_id_middleware
from unstract.core.flask.logging import setup_logging
from unstract.flags.feature_flag import check_feature_flag_status
from unstract.prompt_service.controllers import api
from unstract.prompt_service.helpers.plugin import plugin_loader

if check_feature_flag_status("sdk1"):
    from unstract.sdk1.constants import LogLevel
else:
    from unstract.sdk.constants import LogLevel

load_dotenv()


def create_app() -> Flask:
    """Creates and configures the Flask application."""
    log_level = env.get("LOG_LEVEL", LogLevel.INFO.value).upper()
    setup_logging(log_level)
    log_level = getattr(logging, log_level, logging.INFO)
    app = Flask("prompt-service")
    app.logger.setLevel(log_level)
    app.logger.info("Initializing Flask application...")

    # Load plugins
    plugin_loader(app)
    register_request_id_middleware(app)
    register_error_handlers(app)
    app.register_blueprint(api)

    app.logger.info("Flask app created successfully.")
    return app
