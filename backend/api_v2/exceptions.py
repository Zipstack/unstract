from rest_framework.exceptions import APIException


class NotFoundException(APIException):
    status_code = 404
    default_detail = "The requested resource was not found."


class PathVariablesNotFound(NotFoundException):
    default_detail = "Path variable must be provided."


class MandatoryWorkflowId(APIException):
    status_code = 400
    default_detail = "Workflow ID is mandatory"


class ApiKeyCreateException(APIException):
    status_code = 500
    default_detail = "Exception while create API key"


class Forbidden(APIException):
    status_code = 403
    default_detail = "User is forbidden from performing this action. Please contact admin"


class APINotFound(NotFoundException):
    default_detail = "API not found"


class InvalidAPIRequest(APIException):
    status_code = 400
    default_detail = "Bad request"


class InactiveAPI(NotFoundException):
    default_detail = "API not found or Inactive"


class UnauthorizedKey(APIException):
    status_code = 401
    default_detail = "Unauthorized"


class NoActiveAPIKeyError(APIException):
    status_code = 409
    default_detail = "No active API keys configured for this deployment"

    def __init__(
        self,
        detail: str | None = None,
        code: str | None = None,
        deployment_name: str = "this deployment",
    ):
        if detail is None:
            detail = f"No active API keys configured for {deployment_name}"
        super().__init__(detail, code)


class PresignedURLFetchError(APIException):
    status_code = 400
    default_detail = "Failed to fetch file from presigned URL"

    def __init__(
        self,
        detail: str | None = None,
        code: str | None = None,
        url: str = "",
        error_message: str = "",
    ):
        if detail is None:
            detail = f"Failed to fetch file from URL: {url}. Error: {error_message}"
        super().__init__(detail, code)
