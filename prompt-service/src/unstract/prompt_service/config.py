import logging
from logging.config import dictConfig
from os import environ as env

from dotenv import load_dotenv
from flask import Flask
from unstract.prompt_service.constants import LogLevel

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


def create_app() -> Flask:
    app = Flask("prompt-service")
    log_level = env.get("LOG_LEVEL", LogLevel.WARN)
    if log_level == LogLevel.DEBUG.value:
        app.logger.setLevel(logging.DEBUG)
    elif log_level == LogLevel.INFO.value:
        app.logger.setLevel(logging.INFO)
    else:
        app.logger.setLevel(logging.WARNING)

    return app
