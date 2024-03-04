from rest_framework.exceptions import APIException

from backend.exceptions import UnstractBaseException


class IdIsMandatory(APIException):
    status_code = 400
    default_detail = "ID is Mandatory."


class InValidType(APIException):
    status_code = 400
    default_detail = "Type is not Valid."


class InValidAdapterId(APIException):
    status_code = 400
    default_detail = "Adapter ID is not Valid."


class JSONParseException(APIException):
    status_code = 500
    default_detail = "Exception occured while Parsing JSON Schema."


class InternalServiceError(APIException):
    status_code = 500
    default_detail = "Internal Service error"


class CannotDeleteDefaultAdapter(APIException):
    status_code = 500
    default_detail = (
        "This is configured as default and cannot be deleted. "
        "Please configure a different default before you try again!"
    )


class UniqueConstraintViolation(APIException):
    status_code = 400
    default_detail = "Unique constraint violated"


class TestAdapterException(UnstractBaseException):
    status_code = 500
    default_detail = "Error while testing adapter."


class TestAdapterInputException(UnstractBaseException):
    status_code = 400
    default_detail = "Connection test failed using the given configuration data"


class ErrorFetchingAdapterData(UnstractBaseException):
    status_code = 400
    default_detail = "Error while fetching adapter data."
