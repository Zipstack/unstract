import logging
import os

from dotenv import load_dotenv
from flask import Flask

from unstract.core.flask import register_error_handlers, register_request_id_middleware
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
        database=Env.PG_BE_DATABASE,
        user=Env.PG_BE_USERNAME,
        password=Env.PG_BE_PASSWORD,
        host=Env.PG_BE_HOST,
        port=Env.PG_BE_PORT,
        options=f"-c application_name={Env.APPLICATION_NAME}",
    )

    return app
