from typing import Optional

from rest_framework.exceptions import APIException

from backend.exceptions import UnstractBaseException


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


class UniqueConstraintViolation(APIException):
    status_code = 400
    default_detail = "Unique constraint violated"


class TestAdapterError(UnstractBaseException):
    status_code = 500
    default_detail = "Error while testing adapter"


class DeleteAdapterInUseError(APIException):
    status_code = 409

    def __init__(
        self,
        detail: Optional[str] = None,
        code: Optional[str] = None,
        adapter_name: str = "adapter",
    ):
        if detail is None:
            detail = (
                f"Cannot delete {adapter_name}. "
                "It is used in a workflow or a prompt studio project"
            )
        super().__init__(detail, code)
