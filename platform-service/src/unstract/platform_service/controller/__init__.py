import json
import traceback

from flask import Blueprint, Response, jsonify, request
from werkzeug.exceptions import HTTPException

from unstract.platform_service.controller.health import health_bp
from unstract.platform_service.controller.platform import platform_bp
from unstract.platform_service.exceptions import APIError, ErrorResponse

api = Blueprint("api", __name__)
api.register_blueprint(platform_bp)
api.register_blueprint(health_bp)


def log_exceptions(e: HTTPException) -> None:
    """Helper method to log exceptions.

    Args:
        e (HTTPException): Exception to log
    """
    code = 500
    if hasattr(e, "code"):
        code = e.code or code

    if code >= 500:
        message = f"{request.method} {request.url} {code}\n\n{str(e)}\n\n````{traceback.format_exc()}````"
    else:
        message = f"{request.method} {request.url} {code} {str(e)}"

    # Avoids circular import errors while initializing app context
    from flask import current_app as app

    app.logger.error(message)


@api.errorhandler(HTTPException)
def handle_http_exception(e: HTTPException) -> Response | tuple[Response, int]:
    """Return JSON instead of HTML for HTTP errors."""
    log_exceptions(e)
    if isinstance(e, APIError):
        return jsonify(e.to_dict()), e.code
    else:
        response = e.get_response()
        response.data = json.dumps(
            ErrorResponse(error=e.description, name=e.name, code=e.code)
        )
        response.content_type = "application/json"
        return response


@api.errorhandler(Exception)
def handle_uncaught_exception(e: Exception) -> Response | tuple[Response, int]:
    """Handler for uncaught exceptions.

    Args:
        e (Exception): Any uncaught exception
    """
    # pass through HTTP errors
    if isinstance(e, HTTPException):
        return handle_http_exception(e)

    log_exceptions(e)
    return handle_http_exception(APIError())
