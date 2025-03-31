import logging
import os
from logging.config import dictConfig

from flask import g


class RequestIDFilter(logging.Filter):
    """Filter to inject request ID into log records."""

    def filter(self, record):
        record.request_id = getattr(g, "request_id", "N/A") if g else "N/A"
        return True


def setup_logging(log_level: str):
    """Sets up logger for Flask based services
    Args:
        log_level (str): Log level to use. Can be one of
        INFO, DEBUG, WARNING, ERROR
    """
    # Determine if OpenTelemetry trace context should be included in logs
    otel_trace_context = " trace_id:%(otelTraceID)s span_id:%(otelSpanID)s" if os.environ.get('OTEL_TRACES_EXPORTER', 'none').lower() != 'none' else ""
    
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": (
                        "%(levelname)s : [%(asctime)s]"
                        "{pid:%(process)d tid:%(thread)d request_id:%(request_id)s}" + otel_trace_context + " "
                        "%(name)s:- %(message)s"
                    ),
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
