"""API client related exceptions.

These exceptions follow the Single Responsibility Principle by handling
only API-related error scenarios.
"""

from .base_exceptions import WorkerBaseError


class APIClientError(WorkerBaseError):
    """Base exception for API client errors."""

    pass


class APIRequestError(APIClientError):
    """Raised when an API request fails."""

    def __init__(
        self, message: str, status_code: int = None, response_body: str = None, **kwargs
    ):
        super().__init__(message, **kwargs)
        self.status_code = status_code
        self.response_body = response_body


class AuthenticationError(APIClientError):
    """Raised when API authentication fails."""

    pass


class InternalAPIClientError(APIClientError):
    """Raised for internal API client configuration or logic errors."""

    pass


class RateLimitError(APIClientError):
    """Raised when API rate limits are exceeded."""

    def __init__(self, message: str, retry_after: int = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class TimeoutError(APIClientError):
    """Raised when API requests timeout."""

    def __init__(self, message: str, timeout_duration: float = None, **kwargs):
        super().__init__(message, **kwargs)
        self.timeout_duration = timeout_duration
