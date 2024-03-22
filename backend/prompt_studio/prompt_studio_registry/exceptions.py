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
