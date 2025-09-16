"""Exception classes for Unstract AutoGen Adapter."""

from typing import Optional


class UnstractAutoGenError(Exception):
    """Base exception for Unstract AutoGen Adapter errors.

    Attributes:
        message: Error message
        original_error: Original exception that caused this error (if any)
    """

    def __init__(
        self, message: str, original_error: Optional[Exception] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.original_error = original_error

    def __str__(self) -> str:
        if self.original_error:
            return f"{self.message} (caused by: {self.original_error})"
        return self.message


class UnstractConfigurationError(UnstractAutoGenError):
    """Raised when adapter configuration is invalid."""

    pass


class UnstractCompletionError(UnstractAutoGenError):
    """Raised when completion request fails."""

    pass


class UnstractConnectionError(UnstractAutoGenError):
    """Raised when connection to Unstract adapter fails."""

    pass


class UnstractTimeoutError(UnstractAutoGenError):
    """Raised when adapter request times out."""

    pass


class UnstractValidationError(UnstractAutoGenError):
    """Raised when request validation fails."""

    pass
