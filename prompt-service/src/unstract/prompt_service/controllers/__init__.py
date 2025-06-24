from flask import Blueprint

from .answer_prompt import answer_prompt_bp
from .extraction import extraction_bp
from .extraction_v2 import extraction_v2_bp
from .health import health_bp
from .indexing import indexing_bp

api = Blueprint("api", __name__)

# Register blueprint to the API Blueprint
api.register_blueprint(health_bp)
api.register_blueprint(answer_prompt_bp)
api.register_blueprint(indexing_bp)
api.register_blueprint(extraction_bp)
api.register_blueprint(extraction_v2_bp)
