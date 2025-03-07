import uuid
from typing import Any

from flask import Flask, g, request
from unstract.prompt_service_v2.extensions import db


def register_lifecycle_hooks(app: Flask):
    @app.before_request
    def before_request() -> None:
        """Ensure the DB connection is open before handling the request."""
        if db.is_closed():
            db.connect(reuse_if_open=True)
        g.request_id = request.headers.get("X-Request-ID", uuid.uuid4())
        app.logger.info(f"Request Path: {request.path} | Method: {request.method}")

    @app.teardown_request
    def teardown_request(exception: Any) -> None:
        """Close the DB connection after the request is handled."""
        if not db.is_closed():
            db.close()

    @app.after_request
    def log_response_info(response):
        """Log response details."""
        app.logger.info(f"Response Status: {response.status}")
        return response
