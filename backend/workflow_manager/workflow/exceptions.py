from typing import Optional

from rest_framework.exceptions import APIException


class WorkflowGenerationError(APIException):
    status_code = 500
    default_detail = "Error generating workflow."


class WorkflowRegenerationError(APIException):
    status_code = 500
    default_detail = "Error regenerating workflow."


class WorkflowExecutionError(APIException):
    status_code = 400
    default_detail = "Error executing workflow."


class WorkflowDoesNotExistError(APIException):
    status_code = 404
    default_detail = "Workflow does not exist"


class TaskDoesNotExistError(APIException):
    status_code = 404
    default_detail = "Task does not exist"


class DuplicateActionError(APIException):
    status_code = 400
    default_detail = "Action is running"


class InvalidRequest(APIException):
    status_code = 400
    default_detail = "Invalid Request"


class MissingEnvException(APIException):
    status_code = 500
    default_detail = "At least one active platform key should be available."


class InternalException(APIException):
    """Internal Error.

    Args:
        APIException (_type_): _description_
    """

    status_code = 500


class WorkflowExecutionNotExist(APIException):
    status_code = 404
    default_detail = "Workflow execution does not exist"


class WorkflowExecutionBadRequestException(APIException):
    status_code = 400
    default_detail = "Bad request"

    def __init__(
        self, detail: Optional[str] = None, code: Optional[int] = None
    ):
        if detail is not None:
            self.detail = detail
        if code is not None:
            self.code = code
        super().__init__(detail, code)
