from typing import Any

from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

from unstract.connectors.exceptions import ConnectorBaseException


class UnstractBaseException(APIException):
    default_detail = "Error occurred"

    def __init__(
        self,
        detail: str | None = None,
        core_err: ConnectorBaseException | None = None,
        **kwargs: Any,
    ) -> None:
        if detail is None:
            detail = self.default_detail
        if core_err and core_err.user_message:
            detail = core_err.user_message
        if detail and "Name or service not known" in str(detail):
            detail = "Failed to establish a new connection: " "Name or service not known"
        super().__init__(detail=detail, **kwargs)
        self._core_err = core_err


class LLMHelperError(Exception):
    pass


def custom_exception_handler(exc, context) -> Response:  # type: ignore
    response = exception_handler(exc, context)

    if response is not None:
        response.data["status_code"] = response.status_code

    return response


class UnstractFSException(UnstractBaseException):
    """Handles all error from fs connector class and propagates the error
    message to UI.

    Args:
        UnstractBaseException: Inherits class UnstractBaseException
    """

    default_detail = "Error testing connection. "
    status_code = 500
