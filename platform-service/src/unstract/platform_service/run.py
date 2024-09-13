from logging.config import dictConfig

from dotenv import load_dotenv
from flask import Flask
from unstract.platform_service.controller import api

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


if __name__ == "__main__":
    # Start the server
    app.run(host="0.0.0.0", port=3001, load_dotenv=True)
