import uuid

from log_request_id.middleware import RequestIDMiddleware


class CustomRequestIDMiddleware(RequestIDMiddleware):

    def _generate_id(self):
        return str(uuid.uuid4())
