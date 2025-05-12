"""Gmail connector implementation."""

import json
import logging
import os
from datetime import datetime
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from unstract.connectors.email.exceptions import (
    EmailAuthenticationError,
    EmailFetchError,
)
from unstract.connectors.email.unstract_email import UnstractEmail
from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.gcs_helper import GCSHelper

logger = logging.getLogger(__name__)


class UnstractGmail(UnstractEmail):
    """Gmail connector using OAuth2."""

    def __init__(self, settings: dict[str, Any]):
        super().__init__("Gmail")
        try:
            self.client_secrets = json.loads(
                GCSHelper().get_secret("gmail_client_secret")
            )
            self.credentials = Credentials(
                token=settings["access_token"],
                refresh_token=settings["refresh_token"],
                token_uri=self.client_secrets["web"]["token_uri"],
                client_id=self.client_secrets["web"]["client_id"],
                client_secret=self.client_secrets["web"]["client_secret"],
            )
            self.service = build("gmail", "v1", credentials=self.credentials)
        except Exception as e:
            raise EmailAuthenticationError(f"Failed to initialize Gmail: {str(e)}") from e

    @staticmethod
    def get_id() -> str:
        return "gmail|e4a1c890-7b23-4c87-9f21-ac4812c6541a"

    @staticmethod
    def get_name() -> str:
        return "Gmail"

    @staticmethod
    def get_description() -> str:
        return "Access emails and attachments from Gmail"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/Gmail.png"

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
        return "google-oauth2"

    def _build_query(self, search_criteria: dict[str, Any] | None = None) -> str:
        """Build Gmail API query string from search criteria."""
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
                date = date.strftime("%Y/%m/%d")
            query_parts.append(f"after:{date}")
        if "before" in search_criteria:
            date = search_criteria["before"]
            if isinstance(date, datetime):
                date = date.strftime("%Y/%m/%d")
            query_parts.append(f"before:{date}")
        if "has_attachment" in search_criteria:
            if search_criteria["has_attachment"]:
                query_parts.append("has:attachment")

        return " ".join(query_parts)

    def get_emails(
        self,
        folder: str = "INBOX",
        search_criteria: dict[str, Any] | None = None,
        limit: int = 100,
        include_attachments: bool = True,
    ) -> list[dict[str, Any]]:
        """Retrieve emails from Gmail."""
        try:
            query = self._build_query(search_criteria)
            messages = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=limit, labelIds=[folder])
                .execute()
                .get("messages", [])
            )

            emails = []
            for msg in messages:
                email = (
                    self.service.users()
                    .messages()
                    .get(userId="me", id=msg["id"], format="full")
                    .execute()
                )

                headers = {
                    header["name"]: header["value"]
                    for header in email["payload"]["headers"]
                }

                email_data = {
                    "id": email["id"],
                    "subject": headers.get("Subject", ""),
                    "from": headers.get("From", ""),
                    "to": [addr.strip() for addr in headers.get("To", "").split(",")],
                    "date": datetime.fromtimestamp(int(email["internalDate"]) / 1000),
                    "body": "",
                }

                # Extract body and attachments
                if "parts" in email["payload"]:
                    parts = email["payload"]["parts"]
                else:
                    parts = [email["payload"]]

                attachments = []
                for part in parts:
                    if include_attachments and "filename" in part and part["filename"]:
                        attachment = {
                            "filename": part["filename"],
                            "content_type": part["mimeType"],
                            "size": int(part["body"].get("size", 0)),
                        }
                        if "attachmentId" in part["body"]:
                            attachment_data = (
                                self.service.users()
                                .messages()
                                .attachments()
                                .get(
                                    userId="me",
                                    messageId=email["id"],
                                    id=part["body"]["attachmentId"],
                                )
                                .execute()
                            )
                            attachment["content"] = attachment_data["data"]
                        attachments.append(attachment)
                    elif part["mimeType"] == "text/plain":
                        if "data" in part["body"]:
                            email_data["body"] = part["body"]["data"]
                if include_attachments:
                    email_data["attachments"] = attachments

                emails.append(email_data)

            return emails

        except HttpError as error:
            raise EmailFetchError(
                f"Failed to fetch Gmail messages: {str(error)}"
            ) from error
        except Exception as e:
            raise ConnectorError(
                f"Unexpected error fetching Gmail messages: {str(e)}"
            ) from e

    def test_credentials(self) -> bool:
        """Test Gmail credentials by listing labels."""
        try:
            self.service.users().labels().list(userId="me").execute()
            return True
        except HttpError as error:
            raise EmailAuthenticationError(
                f"Failed to authenticate with Gmail: {str(error)}"
            ) from error
        except Exception as e:
            raise ConnectorError(
                f"Unexpected error testing Gmail credentials: {str(e)}"
            ) from e
