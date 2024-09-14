from logging.config import dictConfig
from typing import Any

from dotenv import load_dotenv
from flask import Flask
from unstract.platform_service.controller import api
from unstract.platform_service.controller.platform import be_db

load_dotenv()

dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            }
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            }
        },
        "root": {"level": "INFO", "handlers": ["wsgi"]},
    }
)


def create_app() -> Flask:
    app = Flask("platform_service")

    app.register_blueprint(api)
    return app


app = create_app()


@app.before_request
def before_request() -> None:
    if be_db.is_closed():
        be_db.connect(reuse_if_open=True)


@app.teardown_request
def after_request(exception: Any) -> None:
    # Close the connection after each request
    if not be_db.is_closed():
        be_db.close()


if __name__ == "__main__":
    # Start the server
    app.run(host="0.0.0.0", port=3001, load_dotenv=True)
