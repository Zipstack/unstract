from typing import Optional

from rest_framework.exceptions import APIException

from backend.exceptions import UnstractBaseException
from unstract.connectors.exceptions import ConnectorError


class InvalidInputDirectory(APIException):
    status_code = 400
    default_detail = "The provided path is not a valid directory."

    def __init__(
        self,
        dir: Optional[str] = None,
        detail: Optional[str] = None,
        code: Optional[str] = None,
    ):
        if dir:
            detail = self.default_detail.replace("path", f"path '{dir}'")
        super().__init__(detail, code)


class InvalidSourceConnectionType(APIException):
    status_code = 400
    default_detail = "The provided source connection type is invalid."


class InvalidDestinationConnectionType(APIException):
    status_code = 400
    default_detail = "The provided destination connection type is invalid."


class MissingSourceConnectionType(APIException):
    status_code = 400
    default_detail = "The source connection type is missing."


class MissingDestinationConnectionType(APIException):
    status_code = 400
    default_detail = "The destination connection type is missing."


class SourceConnectorNotConfigured(APIException):
    status_code = 400
    default_detail = "The source connector is not configured"


class DestinationConnectorNotConfigured(APIException):
    status_code = 400
    default_detail = "The destination connector is not configured"


class FileHashNotFound(APIException):
    status_code = 500
    default_detail = "Internal server error: File hash not found."


class FileHashMismatched(APIException):
    status_code = 400
    default_detail = (
        "The file's hash does not match the expected value. "
        "The file may have been altered."
    )


class ToolMetadataNotFound(APIException):
    status_code = 500
    default_detail = "Internal server error: Tool metadata not found."


class OrganizationIdNotFound(APIException):
    status_code = 404
    default_detail = "The organization ID could not be found"


class InvalidToolOutputType(APIException):
    status_code = 500
    default_detail = "Invalid output type is returned from tool"


class ToolOutputTypeMismatch(APIException):
    status_code = 400
    default_detail = (
        "The data type of the tool's output does not match the expected type."
    )


class BigQueryTableNotFound(APIException):
    status_code = 400
    default_detail = (
        "Please enter correct correct bigquery table in the form "
        "{table}.{schema}.{database}."
    )


class UnstractDBException(APIException):
    default_detail = "Error creating/inserting to database. "

    def __init__(self, detail: str = default_detail) -> None:
        status_code = 500
        super().__init__(detail=detail, code=status_code)


class UnstractQueueException(APIException):
    default_detail = "Error creating/inserting to Queue. "

    def __init__(self, detail: str = default_detail) -> None:
        status_code = 500
        super().__init__(detail=detail, code=status_code)


class UnstractFSException(UnstractBaseException):
    def __init__(self, core_err: ConnectorError) -> None:
        super().__init__(detail=core_err.message, core_err=core_err)
        self.default_detail = core_err.message
        self.status_code = 500
