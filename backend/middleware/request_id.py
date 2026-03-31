import uuid

from django.http import HttpRequest, HttpResponse
from log_request_id.middleware import RequestIDMiddleware


class CustomRequestIDMiddleware(RequestIDMiddleware):
    def _generate_id(self):
        return str(uuid.uuid4())

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        """Suppress verbose socket logs and normalize response codes."""
        if "/api/v1/socket" in request.path:
            response.status_code = 200
            return response
        return super().process_response(request, response)
