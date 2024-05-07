from dataclasses import asdict, dataclass
from typing import Any, Optional

from werkzeug.exceptions import HTTPException

DEFAULT_ERR_MESSAGE = "Something went wrong"


@dataclass
class ErrorResponse:
    """Represents error response from prompt service."""

    error: str = DEFAULT_ERR_MESSAGE
    name: str = "PromptServiceError"
    code: int = 500
    payload: Optional[Any] = None


class APIError(HTTPException):
    code = 500

    def __init__(
        self,
        message: str = DEFAULT_ERR_MESSAGE,
        code: Optional[int] = None,
        payload: Any = None,
    ):
        super().__init__(description=message)
        self.message = message
        if code is not None:
            self.code = code
        self.payload = payload

    def to_dict(self):
        err = ErrorResponse(
            error=self.message,
            code=self.code,
            payload=self.payload,
            name=self.__class__.__name__,
        )
        return asdict(err)

    def __str__(self):
        return str(self.message)
