from typing import Optional

from adapter_processor.constants import AdapterKeys
from rest_framework.exceptions import APIException


class IdIsMandatory(APIException):
    status_code = 400
    default_detail = "ID is Mandatory."


class InValidType(APIException):
    status_code = 400
    default_detail = "Type is not Valid."


class InValidAdapterId(APIException):
    status_code = 400
    default_detail = "Adapter ID is not Valid."


class InternalServiceError(APIException):
    status_code = 500
    default_detail = "Internal Service error"


class CannotDeleteDefaultAdapter(APIException):
    status_code = 500
    default_detail = (
        "This is configured as default and cannot be deleted. "
        "Please configure a different default before you try again!"
    )


class DuplicateAdapterNameError(APIException):
    status_code = 400
    default_detail: str = AdapterKeys.ADAPTER_NAME_EXISTS

    def __init__(
        self,
        name: Optional[str] = None,
        detail: Optional[str] = None,
        code: Optional[str] = None,
    ) -> None:
        if name:
            detail = self.default_detail.replace("this name", f"name '{name}'")
        super().__init__(detail, code)


class TestAdapterError(APIException):
    status_code = 500
    default_detail = "Error while testing adapter"


class TestAdapterInputError(APIException):
    status_code = 400
    default_detail = "Error while testing adapter, please check the configuration."


class DeleteAdapterInUseError(APIException):
    status_code = 409

    def __init__(
        self,
        detail: Optional[str] = None,
        code: Optional[str] = None,
        adapter_name: str = "adapter",
    ):
        if detail is None:
            if adapter_name != "adapter":
                adapter_name = f"'{adapter_name}'"
            detail = (
                f"Cannot delete {adapter_name}. "
                "It is used in a workflow or a prompt studio project"
            )
        super().__init__(detail, code)
