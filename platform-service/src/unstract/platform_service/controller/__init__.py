from typing import Any

from flask import Blueprint, Response, jsonify
from unstract.platform_service.exceptions import CustomException

from .health import health_bp
from .platform import platform_bp

api = Blueprint("api", __name__)
api.register_blueprint(platform_bp)
api.register_blueprint(health_bp)


@api.errorhandler(CustomException)
def handle_custom_exception(error: Any) -> tuple[Response, Any]:
    response = jsonify({"error": error.message})
    response.status_code = error.code  # You can customize the HTTP status code
    return jsonify(response), error.code
