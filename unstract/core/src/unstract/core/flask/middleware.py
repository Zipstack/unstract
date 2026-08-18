import uuid

from flask import Flask, g, request


def _incoming_request_id() -> str:
    """Adopt the caller's id, or mint one.

    Unlike the Django backend these services are not internet-facing: every
    caller is another Unstract service forwarding an id, so honouring it is the
    whole point. The id still lands unescaped in every log line and in the echoed
    response header, so only the canonical UUID our services emit is accepted --
    which bounds length and rules out the control characters that would let a
    caller forge a log record.
    """
    request_id = request.headers.get("X-Request-ID")
    try:
        if request_id and str(uuid.UUID(request_id)) == request_id:
            return request_id
    except (AttributeError, TypeError, ValueError):
        pass
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
