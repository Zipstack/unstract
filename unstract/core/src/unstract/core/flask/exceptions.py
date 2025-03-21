"""Flask exception handling utilities."""

import traceback
from dataclasses import asdict, dataclass
from typing import Any, Optional

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

DEFAULT_ERR_MESSAGE = "An unexpected error occurred"


@dataclass
class ErrorResponse:
    """Represents error response from Flask services."""

    error: str = DEFAULT_ERR_MESSAGE
    name: str = "ServiceError"
    code: int = 500
    payload: Optional[Any] = None


class APIError(HTTPException):
    """Base API error class for Flask services."""

    code = 500
    message = DEFAULT_ERR_MESSAGE

    def __init__(
        self,
        message: Optional[str] = None,
        code: Optional[int] = None,
        payload: Any = None,
    ):
        if message:
            self.message = message
        if code:
            self.code = code
        self.payload = payload
        super().__init__(description=message)

    def to_dict(self):
        """Convert error to dictionary format."""
        err = ErrorResponse(
            error=self.message,
            code=self.code,
            payload=self.payload,
            name=self.__class__.__name__,
        )
        return asdict(err)

    def __str__(self):
        return str(self.message)


def log_exceptions(e: HTTPException, logger):
    """Helper method to log exceptions.

    Args:
        e (HTTPException): Exception to log
        logger: Flask application logger instance
    """
    code = 500
    if hasattr(e, "code"):
        code = e.code or code

    if code >= 500:
        message = "{method} {url} {status}\n\n{error}\n\n````{tb}````".format(
            method=request.method,
            url=request.url,
            status=code,
            error=str(e),
            tb=traceback.format_exc(),
        )
    else:
        message = "{method} {url} {status} {error}".format(
            method=request.method,
            url=request.url,
            status=code,
            error=str(e),
        )
    logger.error(message)


def register_error_handlers(app: Flask):
    """Set up Flask error handlers for the application.

    Args:
        app: Flask application instance
    """

    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        """Return JSON instead of HTML for HTTP errors."""
        log_exceptions(e, app.logger)
        if isinstance(e, APIError):
            return jsonify(e.to_dict()), e.code
        else:
            response = e.get_response()
            response.data = jsonify(
                ErrorResponse(error=e.description, name=e.name, code=e.code)
            ).data
            response.content_type = "application/json"
            return response

    @app.errorhandler(Exception)
    def handle_uncaught_exception(e):
        """Handler for uncaught exceptions.

        Args:
            e (Exception): Any uncaught exception
        """
        # pass through HTTP errors
        if isinstance(e, HTTPException):
            return handle_http_exception(e)

        log_exceptions(e, app.logger)
        return handle_http_exception(APIError())
