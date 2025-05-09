from rest_framework.exceptions import APIException


class InvalidInputDirectory(APIException):
    status_code = 400
    default_detail = "The provided path is not a valid directory."

    def __init__(
        self,
        dir: str | None = None,
        detail: str | None = None,
        code: str | None = None,
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
    default_detail = "Unsupported output type is returned from tool"


class ToolOutputTypeMismatch(APIException):
    status_code = 500
    default_detail = "The tool's output type does not match the expected type"

    def __init__(self, detail: str | None = None, code: str | None = None):
        detail += (
            ". Please report this error to the administrator for further assistance."
        )
        super().__init__(detail, code)


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


class SourceFileOrInfilePathNotFound(APIException):
    default_detail = "Error getting source or infile"

    def __init__(self, detail: str = default_detail, code=None):
        status_code = 500
        super().__init__(detail=detail, code=status_code)
