import ast
from typing import Any, Optional

from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler
from unstract.adapters.exceptions import AdapterError

from unstract.connectors.exceptions import ConnectorBaseException


class UnstractBaseException(APIException):
    default_detail = "Error occurred"

    def __init__(
        self,
        detail: Optional[AdapterError] = None,
        core_err: Optional[ConnectorBaseException] = None,
        **kwargs: Any,
    ) -> None:
        if detail and "Name or service not known" in str(detail):
            detail = (
                "Failed to establish a new connection: "
                "Name or service not known"
            )
        else:
            if detail is None:
                detail = self.default_detail
            if core_err and core_err.user_message:
                detail = core_err.user_message
            if detail and detail.message:
                message = detail.message
                start = message.find("{")
                dict_str = message[start:]
                error_object = ast.literal_eval(dict_str)
                err_message = (
                    error_object["message"] or error_object["error"]["message"]
                )
                detail = err_message
        super().__init__(detail=detail, **kwargs)
        self._core_err = core_err


class LLMHelperError(Exception):
    pass


def custom_exception_handler(exc, context) -> Response:  # type: ignore
    response = exception_handler(exc, context)

    if response is not None:
        response.data["status_code"] = response.status_code

    return response
