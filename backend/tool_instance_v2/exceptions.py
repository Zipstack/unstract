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


class AdapterResolutionError(ToolInstanceBaseException):
    """Raised when an adapter name cannot be resolved to an adapter ID during migration."""

    status_code = 400
    default_detail = "Failed to resolve adapter name to adapter ID"

    def __init__(
        self,
        adapter_name: str,
        adapter_type: str,
        available_adapters: list[str] = None,
        tool_name: str = None,
    ):
        if available_adapters:
            available_list = "', '".join(available_adapters)
            detail = (
                f"Tool '{tool_name or 'Unknown'}' references adapter '{adapter_name}' "
                f"of type '{adapter_type}' which no longer exists. "
                f"Available {adapter_type} adapters: ['{available_list}']. "
                f"Please update the tool configuration to use a valid adapter."
            )
        else:
            detail = (
                f"Tool '{tool_name or 'Unknown'}' references adapter '{adapter_name}' "
                f"of type '{adapter_type}' which no longer exists. "
                f"Please update the tool configuration to use a valid adapter."
            )
        super().__init__(detail, tool_name=tool_name)


class OrphanedAdapterError(ToolInstanceBaseException):
    """Raised when a tool references an adapter that has been deleted or is inaccessible."""

    status_code = 400
    default_detail = "Tool references an orphaned adapter"

    def __init__(self, adapter_name: str, tool_instance_id: str, tool_name: str = None):
        detail = (
            f"Tool instance '{tool_instance_id}' contains orphaned adapter reference '{adapter_name}'. "
            f"This adapter may have been deleted or renamed. Please reconfigure the tool to use a valid adapter."
        )
        super().__init__(detail, tool_name=tool_name)
