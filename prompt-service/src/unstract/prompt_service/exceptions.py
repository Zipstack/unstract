from dataclasses import asdict, dataclass
from typing import Any, Optional

from werkzeug.exceptions import HTTPException

DEFAULT_ERR_MESSAGE = "Error from prompt service"


@dataclass
class ErrorResponse:
    """Represents error response from prompt service."""

    error: str = DEFAULT_ERR_MESSAGE
    name: str = "PromptServiceError"
    code: int = 500
    payload: Optional[Any] = None


class APIError(HTTPException):
    code = 500
    message = DEFAULT_ERR_MESSAGE

    def __init__(
        self,
        message: Optional[str] = None,
        code: Optional[int] = None,
        payload: Any = None,
    ):
        if message:
            self.message = message
        if code:
            self.code = code
        self.payload = payload
        super().__init__(description=message)

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


class NoPayloadError(APIError):
    code = 400
    message = "Bad Request / No payload"


class RateLimitError(APIError):
    code = 429
    message = "Running into rate limit errors, please try again later"
