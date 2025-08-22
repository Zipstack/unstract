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
    default_detail = "Failed to fetch file from presigned URL"
    
    def __init__(
        self,
        url: str = "",
        error_message: str = "",
        status_code: int = 400,
        detail: str | None = None,
        code: str | None = None,
    ):
        if detail is None:
            detail = f"Failed to fetch file from URL: {url}. Error: {error_message}"
        
        self.status_code = status_code
        super().__init__(detail, code)
    
    @classmethod
    def from_response_error(cls, url: str, response_status: int, error_message: str = ""):
        """Create exception with status code derived from HTTP response"""
        return cls(url=url, error_message=error_message, status_code=response_status)
    
    @classmethod  
    def from_request_exception(cls, url: str, exception: Exception):
        """Create exception with status code inferred from exception type"""
        status_code = 400  # default
        if isinstance(exception, TimeoutError):
            status_code = 504
        elif "connection" in str(exception).lower():
            status_code = 502
            
        return cls(url=url, error_message=str(exception), status_code=status_code)
