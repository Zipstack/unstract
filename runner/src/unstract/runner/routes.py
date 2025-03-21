from flask import Flask

from .controller import health_bp, run_bp


def register_blueprints(app: Flask):
    app.register_blueprint(blueprint=health_bp, url_prefix="/v1/api")
    app.register_blueprint(blueprint=run_bp, url_prefix="/v1/api")
