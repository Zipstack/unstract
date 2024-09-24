from typing import Literal

from flask import Blueprint

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"], endpoint="health_check")
def health_check() -> str:
    return "OK"


@health_bp.route("/ping", methods=["GET"])
def ping() -> Literal["Pong"]:
    return "Pong"
