import logging
from logging.config import dictConfig
from os import environ as env

from dotenv import load_dotenv
from flask import Flask
from flask.logging import default_handler
from unstract.prompt_service_v2.controllers import api
from unstract.prompt_service_v2.extensions import db
from unstract.prompt_service_v2.helper.lifecycle_helper import register_lifecycle_hooks
from unstract.prompt_service_v2.helper.plugin_helper import plugin_loader
from unstract.prompt_service_v2.utils.env_loader import get_env_or_die
from unstract.prompt_service_v2.utils.request_id_filter import RequestIDFilter
from unstract.sdk.constants import LogLevel

load_dotenv()
dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            }
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            }
        },
        "root": {"level": "INFO", "handlers": ["wsgi"]},
    }
)


def setup_logging(log_level):
    dictConfig(
        {
            "version": 1,
            "formatters": {
                "default": {
                    "format": (
                        "[%(asctime)s] %(levelname)s in %(name)s (%(module)s) "
                        "[Request ID: %(request_id)s]: %(message)s"
                    ),
                    "datefmt": "%Y-%m-%d %H:%M:%S %z",
                },
            },
            "filters": {
                "request_id": {
                    "()": RequestIDFilter,
                }
            },
            "handlers": {
                "wsgi": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://flask.logging.wsgi_errors_stream",
                    "formatter": "default",
                    "filters": ["request_id"],
                },
            },
            "loggers": {
                "werkzeug": {
                    "level": log_level,
                    "handlers": ["wsgi"],
                    "propagate": False,
                },
                "gunicorn.access": {
                    "level": log_level,
                    "handlers": ["wsgi"],
                    "propagate": False,
                },
                "gunicorn.error": {
                    "level": log_level,
                    "handlers": ["wsgi"],
                    "propagate": False,
                },
            },
            "root": {
                "level": log_level,
                "handlers": ["wsgi"],
            },
        }
    )


def create_app() -> Flask:
    """Creates and configures the Flask application."""

    log_level = env.get("LOG_LEVEL", LogLevel.INFO.value).upper()
    log_level = getattr(logging, log_level, logging.INFO)
    setup_logging(log_level)
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
    app.register_blueprint(api)

    app.logger.info("Flask app created successfully.")
    return app
