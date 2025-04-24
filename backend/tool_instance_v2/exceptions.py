from rest_framework.exceptions import APIException


class ToolInstanceBaseException(APIException):
    def __init__(
        self,
        detail: str | None = None,
        code: int | None = None,
        tool_name: str | None = None,
    ) -> None:
        detail = detail or self.default_detail
        if tool_name is not None:
            detail = f"{detail} Tool: {tool_name}"
        super().__init__(detail, code)


class ToolFunctionIsMandatory(ToolInstanceBaseException):
    status_code = 400
    default_detail = "Tool function is mandatory."


class ToolDoesNotExist(ToolInstanceBaseException):
    status_code = 400
    default_detail = "Tool doesn't exist."


class FetchToolListFailed(ToolInstanceBaseException):
    status_code = 400
    default_detail = "Failed to fetch tool list."


class ToolInstantiationError(ToolInstanceBaseException):
    status_code = 500
    default_detail = "Error instantiating tool."


class BadRequestException(ToolInstanceBaseException):
    status_code = 400
    default_detail = "Invalid input."


class ToolSettingValidationError(APIException):
    status_code = 400
    default_detail = "Error while validating tool's setting."
