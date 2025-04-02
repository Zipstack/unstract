from flask import Blueprint

from .health import health_bp
from .run import run_bp

api = Blueprint("api", __name__)

api.register_blueprint(blueprint=health_bp, url_prefix="/v1/api")
api.register_blueprint(blueprint=run_bp, url_prefix="/v1/api")
