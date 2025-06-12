import logging
from logging.config import dictConfig

from flask import g


class RequestIDFilter(logging.Filter):
    """Filter to inject request ID into log records."""

    def filter(self, record):
        record.request_id = getattr(g, "request_id", "-") if g else "-"
        return True


class OTelFieldFilter(logging.Filter):
    def filter(self, record):
        for attr in ["otelTraceID", "otelSpanID"]:
            if not hasattr(record, attr):
                setattr(record, attr, "-")
        return True


def setup_logging(log_level: int):
    """Sets up logger for Flask based services
    Args:
        log_level (int): Log level to use. Can be one of
        logging.INFO, logging.DEBUG, logging.WARNING, logging.ERROR
    """
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": (
                        "%(levelname)s : [%(asctime)s]"
                        "{pid:%(process)d tid:%(thread)d request_id:%(request_id)s "
                        + "trace_id:%(otelTraceID)s span_id:%(otelSpanID)s "
                        + "%(name)s}:- %(message)s"
                    ),
                },
            },
            "filters": {
                "request_id": {
                    "()": RequestIDFilter,
                },
                "otel_ids": {
                    "()": OTelFieldFilter,
                },
            },
            "handlers": {
                "wsgi": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://flask.logging.wsgi_errors_stream",
                    "formatter": "default",
                    "filters": ["request_id", "otel_ids"],
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
