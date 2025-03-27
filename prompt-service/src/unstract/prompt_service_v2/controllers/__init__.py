from flask import Blueprint

from .answer_prompt_controller import answer_prompt_bp
from .extraction_controller import extraction_bp
from .health_controller import health_bp
from .indexing_controller import indexing_bp

api = Blueprint("api", __name__)

# Register blueprint to the API Blueprint
api.register_blueprint(health_bp)
api.register_blueprint(answer_prompt_bp)
api.register_blueprint(indexing_bp)
api.register_blueprint(extraction_bp)
