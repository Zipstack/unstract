import uuid

from flask import Flask, g, request


def register_request_id_middleware(app: Flask):
    """Adds request ID to each request

    Obtains the ID from header or generates a new one and attaches
    it to Flask's g object.
    """

    @app.before_request
    def assign_request_id():
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    @app.after_request
    def echo_request_id(response):
        # Echo the id back so a caller that did not supply one can learn the
        # value this service minted and correlate its own logs (mirrors the
        # Django backend's REQUEST_ID_RESPONSE_HEADER).
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        return response
