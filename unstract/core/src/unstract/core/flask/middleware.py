import re
import uuid

from flask import Flask, g, request

# An incoming X-Request-ID is caller-supplied and lands in every log line and in
# the echoed response header, so it is only accepted in a shape that cannot forge
# a log record (ANSI/control characters) or bloat one (unbounded length).
SAFE_REQUEST_ID = re.compile(r"\A[A-Za-z0-9._:-]{1,128}\Z")


def _incoming_request_id() -> str:
    request_id = request.headers.get("X-Request-ID")
    if request_id and SAFE_REQUEST_ID.match(request_id):
        return request_id
    return str(uuid.uuid4())


def register_request_id_middleware(app: Flask):
    """Adds request ID to each request

    Obtains the ID from header or generates a new one and attaches
    it to Flask's g object.
    """

    @app.before_request
    def assign_request_id():
        g.request_id = _incoming_request_id()

    @app.after_request
    def echo_request_id(response):
        # Echo the id back so a caller that did not supply one can learn the
        # value this service minted and correlate its own logs (mirrors the
        # Django backend's REQUEST_ID_RESPONSE_HEADER).
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        return response
