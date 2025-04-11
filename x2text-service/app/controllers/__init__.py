from flask import Blueprint

from app.controllers.controller import basic

api = Blueprint("api", __name__)


api.register_blueprint(basic, url_prefix="/x2text")
