from rest_framework.exceptions import APIException


class InternalServiceError(APIException):
    status_code = 500
    default_detail = "Internal error occurred while performing platform key operations."


class UserForbidden(APIException):
    status_code = 403
    default_detail = (
        "User is forbidden from performing this action. Please contact admin."
    )


class KeyCountExceeded(APIException):
    status_code = 403
    default_detail = "Maximum key count is exceeded. Please delete one before generation."


class FoundActiveKey(APIException):
    status_code = 403
    default_detail = "Only one active key allowed at a time."


class ActiveKeyNotFound(APIException):
    status_code = 404
    default_detail = "At least one active platform key should be available"


class InvalidRequest(APIException):
    status_code = 401
    default_detail = "Invalid Request"


class DuplicateData(APIException):
    status_code = 400
    default_detail = "Duplicate Data"

    def __init__(self, detail: str | None = None, code: int | None = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(detail, code)
