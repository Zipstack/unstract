"""POP3 connector implementation."""

import email
import logging
import os
import poplib
from datetime import datetime
from email.header import decode_header
from typing import Any

from unstract.connectors.email.exceptions import (
    EmailAuthenticationError,
    EmailConnectorError,
    EmailFetchError,
)
from unstract.connectors.email.unstract_email import UnstractEmail
from unstract.connectors.exceptions import ConnectorError

logger = logging.getLogger(__name__)


class UnstractPOP3(UnstractEmail):
    """POP3 email connector."""

    def __init__(self, settings: dict[str, Any]):
        super().__init__("POP3")
        self.host = settings["host"]
        self.port = settings.get("port", 995)  # Default POP3S port
        self.username = settings["username"]
        self.password = settings["password"]
        self.use_ssl = settings.get("use_ssl", True)
        self._connection = None

    @staticmethod
    def get_id() -> str:
        return "pop3|a3b1d681-9c8b-4f6b-b972-1a6a095312f5"

    @staticmethod
    def get_name() -> str:
        return "POP3 Email"

    @staticmethod
    def get_description() -> str:
        return "Access emails via POP3 protocol"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/POP3.png"

    @staticmethod
    def requires_oauth() -> bool:
        return False

    @staticmethod
    def python_social_auth_backend() -> str:
        return ""

    @staticmethod
    def get_json_schema() -> str:
        """Get JSON schema for validating connector settings.

        Returns:
            str: JSON schema
        """
        f = open(f"{os.path.dirname(__file__)}/static/json_schema.json")
        schema = f.read()
        f.close()
        return schema

    def _connect(self) -> None:
        """Establish POP3 connection."""
        try:
            if self.use_ssl:
                self._connection = poplib.POP3_SSL(self.host, self.port)
            else:
                self._connection = poplib.POP3(self.host, self.port)

            self._connection.user(self.username)
            self._connection.pass_(self.password)
        except poplib.error_proto as e:
            raise EmailAuthenticationError(f"POP3 authentication failed: {str(e)}") from e
        except Exception as e:
            raise ConnectorError(f"Failed to connect to POP3 server: {str(e)}") from e

    def _disconnect(self) -> None:
        """Close POP3 connection."""
        if self._connection:
            try:
                self._connection.quit()
            except Exception:
                pass
            finally:
                self._connection = None

    def _decode_header(self, header: str) -> str:
        """Decode email header."""
        decoded_header: list[tuple[bytes, str]] = decode_header(header)
        parts = []
        for content, charset in decoded_header:
            if isinstance(content, bytes):
                if charset:
                    parts.append(content.decode(charset))
                else:
                    parts.append(content.decode())
            else:
                parts.append(content)
        return "".join(parts)

    def get_emails(
        self,
        folder: str = "INBOX",
        search_criteria: dict[str, Any] | None = None,
        limit: int = 100,
        include_attachments: bool = True,
    ) -> list[dict[str, Any]]:
        """Retrieve emails via POP3.

        Note: POP3 doesn't support folders or searching, all emails are in a single mailbox.
        The folder parameter is ignored, and search_criteria is applied after fetching.
        """
        try:
            if not self._connection:
                self._connect()

            # Get message count
            message_count = len(self._connection.list()[1])
            start = max(1, message_count - limit + 1)

            emails = []
            for i in range(start, message_count + 1):
                # Retrieve message
                lines = self._connection.retr(i)[1]
                msg_content = b"\n".join(lines).decode("utf-8", errors="ignore")
                email_message = email.message_from_string(msg_content)

                # Apply search criteria if provided
                if search_criteria:
                    if (
                        "from" in search_criteria
                        and search_criteria["from"].lower()
                        not in email_message["from"].lower()
                    ):
                        continue
                    if (
                        "to" in search_criteria
                        and search_criteria["to"].lower()
                        not in email_message["to"].lower()
                    ):
                        continue
                    if (
                        "subject" in search_criteria
                        and search_criteria["subject"].lower()
                        not in email_message["subject"].lower()
                    ):
                        continue

                # Parse email data
                email_data = {
                    "id": str(i),
                    "subject": self._decode_header(email_message["subject"] or ""),
                    "from": self._decode_header(email_message["from"] or ""),
                    "to": [
                        addr.strip()
                        for addr in self._decode_header(email_message["to"] or "").split(
                            ","
                        )
                    ],
                    "date": datetime.strptime(
                        email_message["date"], "%a, %d %b %Y %H:%M:%S %z"
                    ),
                    "body": "",
                }

                attachments = []
                for part in email_message.walk():
                    if part.get_content_maintype() == "text" and not email_data["body"]:
                        email_data["body"] = part.get_payload(decode=True).decode()
                    elif (
                        include_attachments
                        and part.get_content_maintype() != "multipart"
                        and part.get("Content-Disposition")
                    ):
                        filename = part.get_filename()
                        if filename:
                            attachments.append(
                                {
                                    "filename": self._decode_header(filename),
                                    "content_type": part.get_content_type(),
                                    "size": len(part.get_payload(decode=True)),
                                    "content": part.get_payload(decode=True),
                                }
                            )

                if include_attachments:
                    email_data["attachments"] = attachments

                emails.append(email_data)

                # Break if we've reached the limit
                if len(emails) >= limit:
                    break

            return emails

        except poplib.error_proto as e:
            raise EmailFetchError(f"Failed to fetch POP3 messages: {str(e)}") from e
        except Exception as e:
            raise EmailConnectorError(
                f"Unexpected error fetching POP3 messages: {str(e)}"
            ) from e
        finally:
            self._disconnect()

    def test_credentials(self) -> bool:
        """Test POP3 credentials by connecting and getting stats."""
        try:
            self._connect()
            self._connection.stat()  # Get mailbox status
            return True
        except poplib.error_proto as e:
            raise EmailAuthenticationError(
                f"Failed to authenticate with POP3 server: {str(e)}"
            ) from e
        except Exception as e:
            raise EmailConnectorError(
                f"Unexpected error testing POP3 credentials: {str(e)}"
            ) from e
        finally:
            self._disconnect()
