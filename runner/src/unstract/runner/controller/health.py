import logging

from flask import Blueprint, Response, jsonify

logger = logging.getLogger(__name__)

# Define a Blueprint with a root URL path
health_bp = Blueprint("health", __name__)


# Define a route to ping test
@health_bp.route("/health", methods=["GET"])
def health_check() -> str:
    return "OK"
