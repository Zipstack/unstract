"""Custom exceptions for email notification system."""


class EmailNotificationError(Exception):
    """Base exception for email notification errors."""

    pass


class EmailConfigurationError(EmailNotificationError):
    """Raised when email service configuration is invalid."""

    pass


class SendGridAPIError(EmailNotificationError):
    """Raised when SendGrid API call fails."""

    pass


class InvalidRecipientError(EmailNotificationError):
    """Raised when recipient email address is invalid."""

    pass


class TemplateDataError(EmailNotificationError):
    """Raised when template data is invalid or missing required fields."""

    pass
