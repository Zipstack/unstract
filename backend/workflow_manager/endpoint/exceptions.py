from typing import Any

from rest_framework.exceptions import APIException


class InvalidInputDirectory(APIException):
    status_code = 400
    default_detail = "The provided directory is invalid."


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
    status_code = 400
    default_detail = "Error writing to database"

    def __init__(self, code: Any = status_code, detail: str = default_detail) -> None:
        super().__init__(detail=detail, code=code)


class InvalidSyntaxException(UnstractDBException):
    def __init__(self, code: Any, detail: Any) -> None:
        default_detail = "Syntax incorrect. "
        super().__init__(code=code, detail=default_detail + detail)


class InvalidSchemaException(UnstractDBException):
    def __init__(self, code: Any, detail: Any) -> None:
        default_detail = "Schema not valid. "
        super().__init__(code=code, detail=default_detail + detail)


class SnowflakeProgrammingException(UnstractDBException):
    def __init__(self, code: Any, detail: Any) -> None:
        default_detail = "Error while creating/inserting data. "
        super().__init__(code, default_detail + detail)


class BigQueryForbiddenException(UnstractDBException):
    default_detail = "Access forbidden. Check your permissions."

    def __init__(self, code: Any, detail: str = default_detail) -> None:
        super().__init__(detail=detail, code=code)


class BigQueryNotFoundException(UnstractDBException):
    default_detail = "The requested resource was not found."

    def __init__(self, code: Any, detail: str = default_detail) -> None:
        super().__init__(detail=detail, code=code)
