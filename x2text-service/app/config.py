from os import environ as env

from dotenv import load_dotenv
from flask import Flask

from app.controllers import api
from app.models import X2TextAudit, be_db

load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__)

    api_url_prefix = env.get("API_URL_PREFIX", "/api/v1")
    app.register_blueprint(api, url_prefix=api_url_prefix)

    PG_BE_DATABASE = env.get("DB_NAME")
    be_db.init(PG_BE_DATABASE)
    X2TextAudit.create_table()

    return app
