import logging
from os import environ as env

from dotenv import load_dotenv
from flask import Flask
from flask.logging import default_handler
from unstract.prompt_service_v2.controllers import api
from unstract.prompt_service_v2.extensions import db
from unstract.prompt_service_v2.helpers.lifecycle import register_lifecycle_hooks
from unstract.prompt_service_v2.helpers.plugin import plugin_loader
from unstract.prompt_service_v2.utils.env_loader import get_env_or_die
from unstract.sdk.constants import LogLevel

from unstract.core.flask import register_error_handlers, register_request_id_middleware
from unstract.core.flask.logging import setup_logging

load_dotenv()


def create_app() -> Flask:
    """Creates and configures the Flask application."""

    log_level = env.get("LOG_LEVEL", LogLevel.INFO.value).upper()
    setup_logging(log_level)
    log_level = getattr(logging, log_level, logging.INFO)
    app = Flask("prompt-service")
    app.logger.setLevel(log_level)
    app.logger.info("Initializing Flask application...")
    app.logger.removeHandler(default_handler)
    # Load required environment variables
    db_host = get_env_or_die("PG_BE_HOST")
    db_port = get_env_or_die("PG_BE_PORT")
    db_user = get_env_or_die("PG_BE_USERNAME")
    db_pass = get_env_or_die("PG_BE_PASSWORD")
    db_name = get_env_or_die("PG_BE_DATABASE")
    application_name = env.get("APPLICATION_NAME", "unstract-prompt-service")

    # Initialize and connect to the database
    db.init(
        database=db_name,
        user=db_user,
        password=db_pass,
        host=db_host,
        port=db_port,
        options=f"-c application_name={application_name}",
    )

    # Load plugins
    plugin_loader(app)
    register_lifecycle_hooks(app)
    register_request_id_middleware(app)
    register_error_handlers(app)
    app.register_blueprint(api)

    app.logger.info("Flask app created successfully.")
    return app
