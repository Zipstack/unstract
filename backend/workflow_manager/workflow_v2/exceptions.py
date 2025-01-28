from rest_framework.exceptions import APIException


class WorkflowGenerationError(APIException):
    status_code = 500
    default_detail = "Error generating workflow."


class WorkflowRegenerationError(APIException):
    status_code = 500
    default_detail = "Error regenerating workflow."


class WorkflowExecutionError(APIException):
    def __init__(self, message: str, error_code: int = 500):
        self.status_code = error_code
        detail = f"Error executing workflow: {message}"
        super().__init__(detail)


class WorkflowDoesNotExistError(APIException):
    status_code = 404
    default_detail = "Workflow does not exist"


class ExecutionDoesNotExistError(APIException):
    status_code = 404
    default_detail = "Execution does not exist."


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
