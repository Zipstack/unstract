import traceback

from flask import Flask, jsonify, request
from unstract.prompt_service_v2.exceptions import APIError, ErrorResponse
from werkzeug.exceptions import HTTPException


def register_error_handler(app: Flask):

    def log_exceptions(e: HTTPException):
        """Helper method to log exceptions.

        Args:
            e (HTTPException): Exception to log
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
        app.logger.error(message)

    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        """Return JSON instead of HTML for HTTP errors."""
        log_exceptions(e)
        if isinstance(e, APIError):
            return jsonify(e.to_dict()), e.code
        else:
            response = e.get_response()
            response.data = ErrorResponse(
                error=e.description, name=e.name, code=e.code
            ).to_json()
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

        return handle_http_exception(APIError())
