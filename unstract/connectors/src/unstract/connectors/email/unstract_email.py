"""Base class for email connectors."""

import logging
from abc import ABC, abstractmethod
from typing import Any

from unstract.connectors.base import UnstractConnector
from unstract.connectors.enums import ConnectorMode

logger = logging.getLogger(__name__)


class UnstractEmail(UnstractConnector, ABC):
    """Base class for email connectors."""

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    @staticmethod
    def get_connector_mode() -> ConnectorMode:
        """Get the connector mode."""
        return ConnectorMode.EMAIL

    @staticmethod
    def can_write() -> bool:
        """Whether connector supports writing."""
        return False

    @staticmethod
    def can_read() -> bool:
        """Whether connector supports reading."""
        return True

    @abstractmethod
    def get_emails(
        self,
        folder: str = "INBOX",
        search_criteria: dict[str, Any] | None = None,
        limit: int = 100,
        include_attachments: bool = True,
    ) -> list[dict[str, Any]]:
        """Retrieve emails and their attachments from the specified folder.

        Args:
            folder: Email folder to search in (e.g. INBOX, Sent)
            search_criteria: Filtering criteria (date range, sender, subject, etc)
            limit: Maximum number of emails to retrieve
            include_attachments: Whether to include attachments in response

        Returns:
            List of email objects containing:
            {
                "id": str,           # Unique email ID
                "subject": str,      # Email subject
                "from": str,         # Sender email
                "to": List[str],     # List of recipient emails
                "date": datetime,    # Email date
                "body": str,         # Email body
                "attachments": [     # List of attachments if include_attachments=True
                    {
                        "filename": str,
                        "content_type": str,
                        "size": int,
                        "content": bytes
                    }
                ]
            }

        Raises:
            EmailConnectorError: If fetching emails fails
        """
        pass

    @abstractmethod
    def test_credentials(self) -> bool:
        """Test if the email credentials are valid.

        Returns:
            bool: True if credentials are valid

        Raises:
            EmailConnectorError: If testing credentials fails
        """
        pass
