import logging.config
import os

from .constants import Env


class OTelFieldFilter(logging.Filter):
    def filter(self, record):
        for attr in ["otelTraceID", "otelSpanID"]:
            if not hasattr(record, attr):
                setattr(record, attr, "-")
        return True


class RequestIDFilter(logging.Filter):
    """A filter that adds file_execution_id from environment to log records."""

    def filter(self, record):
        record.request_id = os.getenv(Env.FILE_EXECUTION_ID, "-")
        return True


LOG_LEVEL = os.getenv(Env.LOG_LEVEL, "INFO")
logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {"()": RequestIDFilter},
            "otel_ids": {"()": OTelFieldFilter},
        },
        "formatters": {
            "enriched": {
                "format": (
                    "%(levelname)s : [%(asctime)s]"
                    "{module:%(module)s process:%(process)d "
                    "thread:%(thread)d request_id:%(request_id)s "
                    "trace_id:%(otelTraceID)s span_id:%(otelSpanID)s} :- %(message)s"
                ),
            }
        },
        "handlers": {
            "console": {
                "level": LOG_LEVEL,
                "class": "logging.StreamHandler",
                "filters": ["request_id", "otel_ids"],
                "formatter": "enriched",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
        },
    }
)
