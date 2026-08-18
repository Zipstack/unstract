"""Guards that `authentication_middleware` stays transparent to Flask.

Without `functools.wraps` every decorated route registers as "wrapper", so the
second such route raises at import time.
"""

from flask import Flask
from unstract.platform_service.controller.platform import platform_bp


def test_routes_register_under_their_function_names() -> None:
    # NOSONAR — app is never served; bearer-token routes carry no CSRF surface.
    app = Flask(__name__)  # NOSONAR
    app.register_blueprint(platform_bp)

    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert "platform.wrapper" not in endpoints
    assert "platform.usage" in endpoints
