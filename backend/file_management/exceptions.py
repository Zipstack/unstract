from rest_framework.exceptions import APIException

from backend.exceptions import UnstractBaseException


class MissingConnectorParams(APIException):
    status_code = 400
    default_detail = "Missing params in connector metadata"


class ConnectorClassNotFound(APIException):
    status_code = 404
    default_detail = "Connector class does not exist"


class ConnectorInstanceNotFound(APIException):
    status_code = 404
    default_detail = "Connector instance does not exist"


class InternalServerError(APIException):
    status_code = 500
    default_detail = "Unknown exception"


class ConnectorOAuthError(APIException):
    status_code = 401
    default_detail = "Unauthorized client during OAuth"


class ConnectorApiRequestError(APIException):
    status_code = 400
    default_detail = "Failed to stream file"


class InvalidFileType(APIException):
    status_code = 404
    default_detail = "Invalid file type"


class FileListError(UnstractBaseException):
    status_code = 500
    default_detail = "Error occured while listing files"


class FileNotFound(APIException):
    status_code = 404
    default_detail = "Selected file not found in the location."


class EnvRequired(APIException):
    status_code = 404
    default_detail = "Environment variable not set"


class OrgIdNotValid(APIException):
    status_code = 400
    default_detail = "Organization ID is not valid"


class TenantDirCreationError(APIException):
    status_code = 500
    default_detail = "Error while creating a temporary directory for processing"


class ValidationError(APIException):
    status_code = 400
    default_detail = "Validation Error"

    def __init__(self, detail: str | None = None, code: int | None = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__()


class FileDeletionFailed(APIException):
    status_code = 400
    default_detail = "Unable to delete file."

    def __init__(self, detail: str | None = None, code: int | None = None):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__()
