from typing import Optional

from rest_framework.exceptions import APIException


class MandatoryWorkflowId(APIException):
    status_code = 400
    default_detail = "Workflow ID is mandatory"


class ApiKeyCreateException(APIException):
    status_code = 500
    default_detail = "Exception while create API key"

    def __init__(self, detail: Optional[str] = None, code: Optional[int] = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(detail, code)


class Forbidden(APIException):
    status_code = 403
    default_detail = (
        "User is forbidden from performing this action. Please contact admin"
    )

    def __init__(self, detail: Optional[str] = None, code: Optional[int] = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(detail, code)


class APINotFound(APIException):
    status_code = 404
    default_detail = "Api not found"

    def __init__(self, detail: Optional[str] = None, code: Optional[int] = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(detail, code)


class InvalidAPIRequest(APIException):
    status_code = 400
    default_detail = "Bad request"

    def __init__(self, detail: Optional[str] = None, code: Optional[int] = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(detail, code)


class InactiveAPI(APIException):
    status_code = 404
    default_detail = "API not found or Inactive"

    def __init__(self, detail: Optional[str] = None, code: Optional[int] = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(detail, code)


class UnauthorizedKey(APIException):
    status_code = 401
    default_detail = "Unauthorized"

    def __init__(self, detail: Optional[str] = None, code: Optional[int] = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(detail, code)
