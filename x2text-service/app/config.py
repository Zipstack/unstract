import logging
from os import environ as env

from dotenv import load_dotenv
from flask import Flask

from app.controllers import api
from app.logging_util import register_request_id_middleware, setup_logging
from app.models import X2TextAudit, be_db

load_dotenv()


def create_app() -> Flask:
    log_level = getattr(logging, env.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    setup_logging(log_level)

    app = Flask(__name__)

    # Assign/propagate a request_id (X-Request-ID) for cross-service log correlation.
    register_request_id_middleware(app)

    api_url_prefix = env.get("API_URL_PREFIX", "/api/v1")
    app.register_blueprint(api, url_prefix=api_url_prefix)

    PG_BE_DATABASE = env.get("DB_NAME")
    be_db.init(PG_BE_DATABASE)
    X2TextAudit.create_table()

    return app
