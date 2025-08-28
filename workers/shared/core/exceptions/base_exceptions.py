"""Base exception classes for the workers system.

Following the Liskov Substitution Principle, all worker exceptions inherit from
WorkerBaseError, ensuring consistent error handling interfaces.
"""


class WorkerBaseError(Exception):
    """Base exception for all worker-related errors.

    This provides a consistent interface for error handling across all worker
    components, following the Interface Segregation Principle.
    """

    def __init__(self, message: str, details: dict = None, cause: Exception = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}('{self.message}')"

    def to_dict(self) -> dict:
        """Convert exception to dictionary for serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "cause": str(self.cause) if self.cause else None,
        }
