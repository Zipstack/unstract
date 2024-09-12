from rest_framework.exceptions import APIException

from backend.exceptions import UnstractBaseException
from unstract.connectors.exceptions import ConnectorError


class IdIsMandatory(APIException):
    status_code = 400
    default_detail = "ID is Mandatory."


class InValidType(APIException):
    status_code = 400
    default_detail = "Type is not Valid."


class InValidConnectorMode(APIException):
    status_code = 400
    default_detail = "Connector mode is not Valid."


class InValidConnectorId(APIException):
    status_code = 400
    default_detail = "Connector ID is not Valid."


class JSONParseException(APIException):
    status_code = 500
    default_detail = "Exception occured while Parsing JSON Schema."


class OAuthTimeOut(APIException):
    status_code = 408
    default_detail = "Timed out. Please re-authenticate."


class InternalServiceError(APIException):
    status_code = 500
    default_detail = "Internal Service error"


class TestConnectorException(APIException):
    status_code = 500
    default_detail = "Error while testing connector."


class TestConnectorInputError(UnstractBaseException):
    def __init__(self, core_err: ConnectorError) -> None:
        super().__init__(detail=core_err.message, core_err=core_err)
        self.default_detail = core_err.message
        self.status_code = 400
