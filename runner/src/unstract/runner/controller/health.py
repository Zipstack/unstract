import logging

from flask import Blueprint, Response, jsonify

logger = logging.getLogger(__name__)

# Define a Blueprint with a root URL path
health_bp = Blueprint("health", __name__)


# Define a route to ping test
@health_bp.route("/ping", methods=["GET"])
def ping() -> Response:
    logger.info("Ping request received")
    return jsonify({"message": "pong!!!"})
