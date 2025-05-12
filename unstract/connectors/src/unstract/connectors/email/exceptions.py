"""Email connector specific exceptions."""

from unstract.connectors.exceptions import ConnectorError


class EmailConnectorError(ConnectorError):
    """Base exception for email connector errors."""

    pass


class EmailAuthenticationError(EmailConnectorError):
    """Raised when authentication fails."""

    pass


class EmailConnectionError(EmailConnectorError):
    """Raised when connection to email server fails."""

    pass


class EmailFetchError(EmailConnectorError):
    """Raised when fetching emails fails."""

    pass


class AttachmentError(EmailConnectorError):
    """Raised when handling email attachments fails."""

    pass
