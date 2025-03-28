from flask import Blueprint

from .answer_prompt import answer_prompt_bp
from .health import health_bp

api = Blueprint("api", __name__)

# Register blueprint to the API Blueprint
api.register_blueprint(health_bp)
api.register_blueprint(answer_prompt_bp)
