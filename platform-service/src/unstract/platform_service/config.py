import logging
from logging.config import dictConfig

from dotenv import load_dotenv
from flask import Flask
from unstract.platform_service.constants import LogLevel
from unstract.platform_service.controller import api
from unstract.platform_service.env import Env
from unstract.platform_service.extensions import db
from unstract.platform_service.utils import RemoveAccessLogTimestamp

load_dotenv()


dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": (
                    "[%(asctime)s] %(levelname)s in"
                    " %(name)s (%(module)s): %(message)s"
                ),
                "datefmt": "%Y-%m-%d %H:%M:%S %z",
            },
        },
        "filters": {
            "filter_timestamp": {"()": RemoveAccessLogTimestamp},
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            },
            "remove_access_log_timestamp": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "filters": ["filter_timestamp"],
            },
        },
        "loggers": {
            "werkzeug": {
                "level": Env.LOG_LEVEL,
                "handlers": ["remove_access_log_timestamp"],
                "propagate": False,
            },
            "gunicorn.access": {
                "level": Env.LOG_LEVEL,
                "handlers": ["remove_access_log_timestamp"],
                "propagate": False,
            },
            "gunicorn.error": {
                "level": Env.LOG_LEVEL,
                "handlers": ["remove_access_log_timestamp"],
                "propagate": False,
            },
        },
        "root": {
            "level": Env.LOG_LEVEL,
            "handlers": ["wsgi"],
        },
    }
)

LOGGING_LEVELS = {
    LogLevel.DEBUG: logging.DEBUG,
    LogLevel.INFO: logging.INFO,
    LogLevel.WARNING: logging.WARNING,
    LogLevel.ERROR: logging.ERROR,
    LogLevel.CRITICAL: logging.CRITICAL,
}


def create_app() -> Flask:
    app = Flask("platform-service")

    # Set logging level
    logging_level = LOGGING_LEVELS.get(Env.LOG_LEVEL, logging.INFO)
    app.logger.setLevel(logging_level)
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
