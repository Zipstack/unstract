import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from unstract.core.flask import (
    PluginManager,
    register_error_handlers,
    register_request_id_middleware,
)
from unstract.core.flask.logging import setup_logging
from unstract.platform_service.constants import LogLevel
from unstract.platform_service.controller import api
from unstract.platform_service.env import Env
from unstract.platform_service.extensions import db

load_dotenv()


def create_app() -> Flask:
    app = Flask("platform-service")

    # Configure logging
    log_level = os.getenv("LOG_LEVEL", LogLevel.INFO).upper()
    log_level = getattr(logging, log_level, logging.INFO)
    setup_logging(log_level)

    # Register error handlers
    register_error_handlers(app)

    # Register middleware
    register_request_id_middleware(app)

    # Register URL routes
    app.register_blueprint(api)

    # Initialize and connect to the database
    db.init(
        database=Env.DB_NAME,
        user=Env.DB_USER,
        password=Env.DB_PASSWORD,
        host=Env.DB_HOST,
        port=Env.DB_PORT,
        options=f"-c application_name={Env.APPLICATION_NAME}",
    )

    # Load plugins (cloud plugins will be overlaid during build)
    plugins_dir = Path(__file__).parent / "plugins"
    plugins_pkg = "unstract.platform_service.plugins"
    manager = PluginManager(app, plugins_dir, plugins_pkg)
    manager.load_plugins()

    return app
