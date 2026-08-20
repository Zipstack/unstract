"""Request-id-aware logging for the x2text-service.

Deliberately a self-contained copy of ``unstract.core.flask``'s logging rather
than an import: this service does not take the ``unstract-core`` dependency.
"""

import logging
import uuid
from logging.config import dictConfig

from flask import Flask, g, has_request_context, request

# Copy of the canonical format owned by ``unstract.core.flask.logging``; a
# divergence silently splits this service out of the cross-service log query.
LOG_FORMAT = (
    "%(levelname)s : [%(asctime)s]"
    "{module:%(module)s process:%(process)d thread:%(thread)d "
    "request_id:%(request_id)s trace_id:%(otelTraceID)s span_id:%(otelSpanID)s}"
    " :- %(message)s"
)


class RequestIDFilter(logging.Filter):
    """Inject the current request's ``request_id`` into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Only touch the request-scoped ``g`` inside an active request context;
        # outside one (e.g. gunicorn startup logs) fall back to the placeholder.
        record.request_id = (
            getattr(g, "request_id", "-") if has_request_context() else "-"
        )
        return True


class OTelFieldFilter(logging.Filter):
    """Default OpenTelemetry id fields to ``"-"`` when not populated."""

    def filter(self, record: logging.LogRecord) -> bool:
        for attr in ("otelTraceID", "otelSpanID"):
            if not getattr(record, attr, None):
                setattr(record, attr, "-")
        return True


def setup_logging(log_level: int = logging.INFO) -> None:
    """Configure root/werkzeug/gunicorn loggers with the standardized format."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": {"format": LOG_FORMAT}},
            "filters": {
                "request_id": {"()": RequestIDFilter},
                "otel_ids": {"()": OTelFieldFilter},
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
            "root": {"level": log_level, "handlers": ["wsgi"]},
        }
    )


def register_request_id_middleware(app: Flask) -> None:
    """Read ``X-Request-ID`` from each request (or mint one) onto Flask ``g``."""

    @app.before_request
    def _assign_request_id() -> None:
        # Only the canonical UUID our services emit is adopted; see
        # ``unstract.core.flask.middleware`` for why the shape is checked at all.
        request_id = request.headers.get("X-Request-ID")
        try:
            if not (request_id and str(uuid.UUID(request_id)) == request_id):
                request_id = str(uuid.uuid4())
        except (AttributeError, TypeError, ValueError):
            request_id = str(uuid.uuid4())
        g.request_id = request_id

    @app.after_request
    def _echo_request_id(response):
        # Echo the id back so a caller that did not supply one can learn the
        # value this service minted (mirrors the backend's response header).
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        return response
