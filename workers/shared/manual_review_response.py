"""Manual Review Response Models - OSS Compatible Version

This module provides response models for manual review operations that work
in both OSS and enterprise versions. The OSS version provides safe defaults.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ManualReviewResponse:
    """Response model for manual review operations.

    This class provides a consistent interface for manual review responses
    that works in both OSS and enterprise versions.
    """

    success: bool
    data: dict[str, Any] | None = None
    message: str | None = None
    error: str | None = None
    status_code: int = 200

    @classmethod
    def success_response(
        cls,
        data: dict[str, Any] | None = None,
        message: str | None = None,
        status_code: int = 200,
    ) -> "ManualReviewResponse":
        """Create a successful response.

        Args:
            data: Response data
            message: Success message
            status_code: HTTP status code

        Returns:
            ManualReviewResponse indicating success
        """
        return cls(success=True, data=data, message=message, status_code=status_code)

    @classmethod
    def error_response(
        cls, error: str, data: dict[str, Any] | None = None, status_code: int = 400
    ) -> "ManualReviewResponse":
        """Create an error response.

        Args:
            error: Error message
            data: Error data
            status_code: HTTP status code

        Returns:
            ManualReviewResponse indicating error
        """
        return cls(success=False, data=data, error=error, status_code=status_code)

    @classmethod
    def not_available_response(
        cls, message: str = "Manual review not available in OSS version"
    ) -> "ManualReviewResponse":
        """Create a response indicating feature is not available in OSS.

        Args:
            message: Message explaining unavailability

        Returns:
            ManualReviewResponse indicating feature unavailable
        """
        return cls(
            success=True,  # Still successful, just feature not available
            data={"feature_available": False},
            message=message,
            status_code=200,
        )
