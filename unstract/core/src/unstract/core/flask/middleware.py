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
