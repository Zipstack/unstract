from rest_framework.exceptions import APIException


class ConflictError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class MethodNotImplemented(APIException):
    status_code = 501
    default_detail = "Method Not Implemented"


class DuplicateData(APIException):
    status_code = 400
    default_detail = "Duplicate Data"

    def __init__(self, detail: str | None = None, code: int | None = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(detail, code)


class TableNotExistError(APIException):
    status_code = 400
    default_detail = "Unknown Table"

    def __init__(self, detail: str | None = None, code: int | None = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__()


class UserNotExistError(APIException):
    status_code = 400
    default_detail = "Unknown User"

    def __init__(self, detail: str | None = None, code: int | None = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__()


class Forbidden(APIException):
    status_code = 403
    default_detail = "Do not have permission to perform this action."


class UserAlreadyAssociatedException(APIException):
    status_code = 400
    default_detail = "User is already associated with one organization."
