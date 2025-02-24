from flask import Blueprint

from .answer_prompt_controller import answer_prompt_bp

api = Blueprint("api", __name__)

# Register blueprint to the API Blueprint
api.register_blueprint(answer_prompt_bp)
