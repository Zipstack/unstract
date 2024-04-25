from typing import Optional

from rest_framework.exceptions import APIException


class KeyFileNotMountedError(APIException):
    status_code = 500

    def __init__(
        self,
        detail: Optional[str] = None,
        code: Optional[str] = None,
    ):
        if detail is None:
            detail = "Service account key file is not monuted in the environment path."
        super().__init__(detail, code)
