"""Base Notification Provider

Abstract base class for all notification providers. This ensures consistent
interface across different notification types while allowing for specific
implementation details.
"""

from abc import ABC, abstractmethod
from typing import Any

from shared.infrastructure.logging import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class BaseNotificationProvider(ABC):
    """Abstract base class for notification providers.

    All notification providers (webhook, email, SMS, push) should inherit from
    this class and implement the required methods.
    """

    def __init__(self):
        """Initialize the notification provider."""
        self.provider_name = self.__class__.__name__
        logger.debug(f"Initialized {self.provider_name}")

    @abstractmethod
    def send(self, notification_data: dict[str, Any]) -> dict[str, Any]:
        """Send notification using this provider.

        Args:
            notification_data: Dictionary containing all necessary data for sending
                the notification. The structure may vary by provider type.

        Returns:
            Dictionary containing the result of the send operation:
            {
                "success": bool,
                "message": str,
                "details": dict[str, Any],  # Provider-specific details
                "attempts": int,
                "destination": str
            }

        Raises:
            NotificationError: If sending fails critically
        """
        raise NotImplementedError("Subclasses must implement send method")

    @abstractmethod
    def validate(self, notification_data: dict[str, Any]) -> bool:
        """Validate notification data before attempting to send.

        Args:
            notification_data: Dictionary containing notification data

        Returns:
            True if validation passes

        Raises:
            ValueError: If validation fails with specific error message
        """
        raise NotImplementedError("Subclasses must implement validate method")

    def prepare_data(self, notification_data: dict[str, Any]) -> dict[str, Any]:
        """Prepare notification data for sending.

        This method can be overridden by subclasses to perform provider-specific
        data preparation (formatting, serialization, etc.).

        Args:
            notification_data: Raw notification data

        Returns:
            Prepared notification data
        """
        return notification_data

    def get_destination(self, notification_data: dict[str, Any]) -> str:
        """Extract destination from notification data.

        This method should be overridden by subclasses to extract the appropriate
        destination identifier (URL for webhooks, email for email notifications, etc.).

        Args:
            notification_data: Notification data

        Returns:
            String representation of the destination
        """
        return notification_data.get("destination", "unknown")

    def format_success_result(
        self, destination: str, attempts: int = 1, details: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Format successful notification result.

        Args:
            destination: Target destination
            attempts: Number of attempts taken
            details: Provider-specific success details

        Returns:
            Standardized success result
        """
        return {
            "success": True,
            "message": f"{self.provider_name} notification sent successfully",
            "destination": destination,
            "attempts": attempts,
            "details": details or {},
        }

    def format_failure_result(
        self,
        destination: str,
        error: Exception,
        attempts: int = 1,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Format failed notification result.

        Args:
            destination: Target destination
            error: Exception that occurred
            attempts: Number of attempts made
            details: Provider-specific failure details

        Returns:
            Standardized failure result
        """
        return {
            "success": False,
            "message": f"{self.provider_name} notification failed: {str(error)}",
            "destination": destination,
            "attempts": attempts,
            "error": str(error),
            "error_type": error.__class__.__name__,
            "details": details or {},
        }


class NotificationError(Exception):
    """Base exception for notification provider errors."""

    def __init__(
        self, message: str, provider: str | None = None, destination: str | None = None
    ):
        """Initialize notification error.

        Args:
            message: Error message
            provider: Provider name where error occurred
            destination: Target destination
        """
        self.provider = provider
        self.destination = destination
        super().__init__(message)

    def __str__(self) -> str:
        """String representation of the error."""
        error_parts = [super().__str__()]

        if self.provider:
            error_parts.append(f"Provider: {self.provider}")

        if self.destination:
            error_parts.append(f"Destination: {self.destination}")

        return " | ".join(error_parts)


class ValidationError(NotificationError):
    """Exception raised when notification data validation fails."""

    pass


class DeliveryError(NotificationError):
    """Exception raised when notification delivery fails."""

    pass
