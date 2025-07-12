from adapter_processor_v2.constants import AdapterKeys
from rest_framework.exceptions import APIException

from unstract.sdk1.exceptions import SdkError as Sdk1Error
from unstract.sdk.exceptions import SdkError


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
        name: str | None = None,
        detail: str | None = None,
        code: str | None = None,
    ) -> None:
        if name:
            detail = self.default_detail.replace("this name", f"name '{name}'")
        super().__init__(detail, code)


class TestAdapterError(APIException):
    status_code = 500
    default_detail = "Error while testing adapter"

    def __init__(
        self,
        sdk_err: Sdk1Error | SdkError,
        detail: str | None = None,
        code: str | None = None,
        adapter_name: str | None = None,
    ):
        if sdk_err.status_code:
            self.status_code = sdk_err.status_code
        if detail is None:
            adapter_name = f"'{adapter_name}'" if adapter_name else "adapter"
            detail = f"Error testing {adapter_name}. {str(sdk_err)}"
        super().__init__(detail, code)


class TestAdapterInputError(APIException):
    status_code = 400
    default_detail = "Error while testing adapter, please check the configuration."


class DeleteAdapterInUseError(APIException):
    status_code = 409

    def __init__(
        self,
        detail: str | None = None,
        code: str | None = None,
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
