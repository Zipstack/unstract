from rest_framework.exceptions import APIException


class InternalError(APIException):
    status_code = 500
    default_detail = "Internal service error."


class ToolDoesNotExist(APIException):
    status_code = 500
    default_detail = "Tool does not exist."


class ToolSaveError(APIException):
    status_code = 500
    default_detail = "Error while saving the tool."


class EmptyToolExportError(APIException):
    status_code = 500
    default_detail = (
        "Prompt Studio project without prompts cannot be exported. "
        "Please ensure there is at least one active prompt "
        "that has been run before exporting."
    )


class InValidCustomToolError(APIException):
    status_code = 500
    default_detail = (
        "This prompt studio project cannot be exported. It probably "
        "has some empty or unexecuted prompts."
    )
