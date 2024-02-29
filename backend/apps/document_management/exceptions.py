from typing import Optional

from rest_framework.exceptions import APIException


class AppNotFound(APIException):
    status_code = 404
    default_detail = "App does not exist"


class ValidationError(APIException):
    status_code = 400
    default_detail = "Validation Error"

    def __init__(
        self, detail: Optional[str] = None, code: Optional[int] = None
    ):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__()
