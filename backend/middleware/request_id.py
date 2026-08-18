import uuid

from log_request_id.middleware import RequestIDMiddleware

# The internal service boundary: our own workers call back here while executing
# a workflow, forwarding the request_id of the HTTP call that started it.
INTERNAL_PATH_PREFIX = "/internal/"


def _canonical_uuid(value: str | None) -> str | None:
    """Return ``value`` only if it is a canonical hyphenated UUID."""
    try:
        return value if str(uuid.UUID(value)) == value else None
    except (AttributeError, TypeError, ValueError):
        return None


class CustomRequestIDMiddleware(RequestIDMiddleware):
    """Provisions the request id here rather than trusting the caller's.

    Adopting a caller-supplied id lets any client repeat one value across
    unrelated requests. That does not merely lose correlation -- a log query for
    that id returns other tenants' requests and reads as though it worked, which
    is worse than returning nothing. The id also reaches every log line, Celery
    message header and outbound internal-API call, so an unvalidated one can
    forge a log record outright.

    The internal boundary is the exception: there the caller is our own worker
    forwarding the id of the request that started the execution, which is the
    hop that makes worker logs correlate back to the originating call.
    """

    def _get_request_id(self, request):
        if request.path.startswith(INTERNAL_PATH_PREFIX):
            forwarded = _canonical_uuid(request.META.get(self.request_id_header))
            if forwarded:
                return forwarded
        return self._generate_id()

    def _generate_id(self):
        return str(uuid.uuid4())
