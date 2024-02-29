from typing import Optional

from rest_framework.exceptions import APIException


class AppDeploymentBadRequestException(APIException):
    """Exception for bad request - http 400

    Args:
        APIException (_type_): _description_
    """

    status_code = 400
    default_detail = "Bad request"

    def __init__(
        self, detail: Optional[str] = None, code: Optional[int] = None
    ):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(detail, code)
