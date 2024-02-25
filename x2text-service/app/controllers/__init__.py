from app.controllers.controller import basic
from flask import Blueprint

api = Blueprint("api", __name__)


api.register_blueprint(basic, url_prefix="/x2text")
