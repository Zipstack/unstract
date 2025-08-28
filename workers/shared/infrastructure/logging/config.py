"""Shared logging configuration for workers to match Django backend format."""

import logging
import logging.config
import os

# Default log level from environment
DEFAULT_LOG_LEVEL = os.environ.get("DEFAULT_LOG_LEVEL", "INFO")


class WorkerFieldFilter(logging.Filter):
    """Filter to add missing fields for worker logging."""

    def filter(self, record):
        # Add missing fields with default values
        for attr in ["request_id", "otelTraceID", "otelSpanID"]:
            if not hasattr(record, attr):
                setattr(record, attr, "-")
        return True


def setup_worker_logging():
    """Setup logging configuration that matches Django backend format."""
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "worker_fields": {"()": "shared.logging_config.WorkerFieldFilter"},
        },
        "formatters": {
            "enriched": {
                "format": (
                    "%(levelname)s : [%(asctime)s]"
                    "{module:%(module)s process:%(process)d "
                    "thread:%(thread)d request_id:%(request_id)s "
                    "trace_id:%(otelTraceID)s span_id:%(otelSpanID)s} :- %(message)s"
                ),
            },
            "simple": {
                "format": "{levelname} {message}",
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "level": DEFAULT_LOG_LEVEL,
                "class": "logging.StreamHandler",
                "filters": ["worker_fields"],
                "formatter": "enriched",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": DEFAULT_LOG_LEVEL,
        },
    }

    # Configure logging
    logging.config.dictConfig(logging_config)

    return logging.getLogger()


def get_worker_logger(name: str = None) -> logging.Logger:
    """Get a logger configured for worker use."""
    if name:
        return logging.getLogger(name)
    return logging.getLogger()
