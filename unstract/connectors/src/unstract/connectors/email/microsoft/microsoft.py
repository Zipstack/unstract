"""Microsoft Outlook/Exchange connector implementation."""

import json
import logging
import os
from datetime import datetime
from typing import Any

from O365 import Account, Connection
from O365.message import Message

from unstract.connectors.email.exceptions import EmailAuthenticationError, EmailFetchError
from unstract.connectors.email.unstract_email import UnstractEmail
from unstract.connectors.gcs_helper import GCSHelper

logger = logging.getLogger(__name__)


class UnstractMicrosoft(UnstractEmail):
    """Microsoft Outlook/Exchange connector using OAuth2."""

    def __init__(self, settings: dict[str, Any]):
        super().__init__("Microsoft")
        try:
            self.client_secrets = json.loads(
                GCSHelper().get_secret("microsoft_client_secret")
            )
            self.credentials = {
                "token": settings["access_token"],
                "refresh_token": settings["refresh_token"],
                "token_uri": self.client_secrets["web"]["token_uri"],
                "client_id": self.client_secrets["web"]["client_id"],
                "client_secret": self.client_secrets["web"]["client_secret"],
            }
            self.account = Account(
                credentials=(
                    self.client_secrets["web"]["client_id"],
                    self.client_secrets["web"]["client_secret"],
                ),
                token_backend=Connection(self.credentials),
            )
        except Exception as e:
            raise EmailAuthenticationError(
                f"Failed to initialize Microsoft email: {str(e)}"
            ) from e

    @staticmethod
    def get_id() -> str:
        return "microsoft|d4a1c890-7b23-4c87-9f21-ac4812c6541b"

    @staticmethod
    def get_name() -> str:
        return "Microsoft Email"

    @staticmethod
    def get_description() -> str:
        return "Access emails from Microsoft Outlook/Exchange"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/Outlook.png"

    @staticmethod
    def get_json_schema() -> str:
        f = open(f"{os.path.dirname(__file__)}/static/json_schema.json")
        schema = f.read()
        f.close()
        return schema

    @staticmethod
    def requires_oauth() -> bool:
        return True

    @staticmethod
    def python_social_auth_backend() -> str:
        return "microsoft-graph-oauth2"

    def _build_query(self, search_criteria: dict[str, Any] | None = None) -> str:
        """Build Microsoft Graph API query string from search criteria."""
        if not search_criteria:
            return ""

        query_parts = []
        if "from" in search_criteria:
            query_parts.append(f"from:{search_criteria['from']}")
        if "to" in search_criteria:
            query_parts.append(f"to:{search_criteria['to']}")
        if "subject" in search_criteria:
            query_parts.append(f"subject:{search_criteria['subject']}")
        if "after" in search_criteria:
            date = search_criteria["after"]
            if isinstance(date, datetime):
                date = date.strftime("%Y-%m-%d")
            query_parts.append(f"received>={date}")
        if "before" in search_criteria:
            date = search_criteria["before"]
            if isinstance(date, datetime):
                date = date.strftime("%Y-%m-%d")
            query_parts.append(f"received<={date}")
        if "has_attachment" in search_criteria:
            if search_criteria["has_attachment"]:
                query_parts.append("hasAttachments:true")

        return " ".join(query_parts)

    def get_emails(
        self,
        folder: str = "Inbox",
        search_criteria: dict[str, Any] | None = None,
        limit: int = 100,
        include_attachments: bool = True,
    ) -> list[dict[str, Any]]:
        """Retrieve emails from Microsoft Outlook/Exchange."""
        try:
            mailbox = self.account.mailbox()
            mail_folder = mailbox.get_folder(folder_name=folder)
            query = self._build_query(search_criteria)

            messages = list(mail_folder.get_messages(limit=limit, query=query))
            emails = []

            for msg in messages:
                msg: Message
                email_data = {
                    "id": msg.object_id,
                    "subject": msg.subject or "",
                    "from": str(msg.sender) if msg.sender else "",
                    "to": [str(recipient) for recipient in msg.to],
                    "date": msg.received,
                    "body": msg.body or "",
                }

                if include_attachments and msg.has_attachments:
                    attachments = []
                    for attachment in msg.attachments:
                        content = attachment.content
                        if content:
                            attachments.append(
                                {
                                    "filename": attachment.name,
                                    "content_type": attachment.content_type,
                                    "size": len(content),
                                    "content": content,
                                }
                            )
                    email_data["attachments"] = attachments

                emails.append(email_data)

            return emails

        except Exception as e:
            raise EmailFetchError(
                f"Failed to fetch Microsoft email messages: {str(e)}"
            ) from e

    def test_credentials(self) -> bool:
        """Test Microsoft email credentials by listing folders."""
        try:
            mailbox = self.account.mailbox()
            list(mailbox.list_folders())
            return True
        except Exception as e:
            raise EmailAuthenticationError(
                f"Failed to authenticate with Microsoft email: {str(e)}"
            ) from e
