import re
import uuid

from log_request_id.middleware import RequestIDMiddleware

# An incoming X-Request-ID reaches every log line, every published Celery message
# header and every outbound internal-API call, so it is only ever accepted in a
# shape that cannot forge a log record or bloat a message. gunicorn rejects only
# \0\r\n and caps a header field at ~8KB, which leaves ANSI escapes and 8000-char
# values arriving intact; anything not matching here is discarded for a fresh id.
SAFE_REQUEST_ID = re.compile(r"\A[A-Za-z0-9._:-]{1,128}\Z")


class CustomRequestIDMiddleware(RequestIDMiddleware):
    def _get_request_id(self, request):
        request_id = super()._get_request_id(request)
        if request_id and SAFE_REQUEST_ID.match(request_id):
            return request_id
        return self._generate_id()

    def _generate_id(self):
        return str(uuid.uuid4())
