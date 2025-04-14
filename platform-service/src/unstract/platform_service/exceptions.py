from dataclasses import asdict, dataclass
from typing import Any

from werkzeug.exceptions import HTTPException

DEFAULT_ERR_MESSAGE = "Error from platform service"


@dataclass
class ErrorResponse:
    """Represents error response from platform service."""

    error: str = DEFAULT_ERR_MESSAGE
    name: str = "PlatformServiceError"
    code: int = 500
    payload: Any | None = None


class APIError(HTTPException):
    code = 500
    message = DEFAULT_ERR_MESSAGE

    def __init__(
        self,
        message: str | None = None,
        code: int | None = None,
        payload: Any = None,
    ):
        if message:
            self.message = message
        if code:
            self.code = code
        self.payload = payload
        super().__init__(description=message)

    def to_dict(self) -> dict[str, Any]:
        err = ErrorResponse(
            error=self.message,
            code=self.code,
            payload=self.payload,
            name=self.__class__.__name__,
        )
        return asdict(err)

    def __str__(self) -> str:
        return str(self.message)
