import uuid

from django.http import HttpRequest
from log_request_id.middleware import RequestIDMiddleware


# django-log-request-id ships no type hints.
class CustomRequestIDMiddleware(RequestIDMiddleware):  # type: ignore[misc]
    """Logs and echoes the client's X-Request-ID when it is a UUID, else a new one.

    The check keeps arbitrary client text out of the logs.
    """

    def _generate_id(self) -> str:
        return str(uuid.uuid4())

    def _get_request_id(self, request: HttpRequest) -> str:
        incoming = request.META.get(self.request_id_header or "", "")
        try:
            return str(uuid.UUID(incoming))
        except ValueError:
            return self._generate_id()
