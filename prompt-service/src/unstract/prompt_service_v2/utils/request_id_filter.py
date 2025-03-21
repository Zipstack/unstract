import logging

from flask import g


class RequestIDFilter(logging.Filter):
    """Filter to inject request ID into log records."""

    def filter(self, record):
        record.request_id = getattr(g, "request_id", "N/A") if g else "N/A"
        return True
