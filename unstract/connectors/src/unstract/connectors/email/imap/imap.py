"""IMAP connector implementation."""

import email
import imaplib
import logging
import os
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


class UnstractIMAP(UnstractEmail):
    """IMAP email connector."""

    def __init__(self, settings: dict[str, Any]):
        super().__init__("IMAP")
        self.host = settings["host"]
        self.port = settings.get("port", 993)  # Default IMAPS port
        self.username = settings["username"]
        self.password = settings["password"]
        self.use_ssl = settings.get("use_ssl", True)
        self._connection = None

    @staticmethod
    def get_id() -> str:
        return "imap|f2b1d681-9c8b-4f6b-b972-1a6a095312f4"

    @staticmethod
    def get_name() -> str:
        return "IMAP Email"

    @staticmethod
    def get_description() -> str:
        return "Access emails via IMAP protocol"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/IMAP.png"

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
        """Establish IMAP connection."""
        try:
            if self.use_ssl:
                self._connection = imaplib.IMAP4_SSL(self.host, self.port)
            else:
                self._connection = imaplib.IMAP4(self.host, self.port)

            self._connection.login(self.username, self.password)
        except imaplib.IMAP4.error as e:
            raise EmailAuthenticationError(f"IMAP authentication failed: {str(e)}") from e
        except Exception as e:
            raise ConnectorError(f"Failed to connect to IMAP server: {str(e)}") from e

    def _disconnect(self) -> None:
        """Close IMAP connection."""
        if self._connection:
            try:
                self._connection.logout()
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

    def _build_search_criteria(
        self, search_criteria: dict[str, Any] | None = None
    ) -> list[str]:
        """Build IMAP search criteria."""
        if not search_criteria:
            return ["ALL"]

        criteria = []
        if "from" in search_criteria:
            criteria.extend(["FROM", search_criteria["from"]])
        if "to" in search_criteria:
            criteria.extend(["TO", search_criteria["to"]])
        if "subject" in search_criteria:
            criteria.extend(["SUBJECT", search_criteria["subject"]])
        if "after" in search_criteria:
            date = search_criteria["after"]
            if isinstance(date, datetime):
                date = date.strftime("%d-%b-%Y")
            criteria.extend(["SINCE", date])
        if "before" in search_criteria:
            date = search_criteria["before"]
            if isinstance(date, datetime):
                date = date.strftime("%d-%b-%Y")
            criteria.extend(["BEFORE", date])

        return criteria or ["ALL"]

    def get_emails(
        self,
        folder: str = "INBOX",
        search_criteria: dict[str, Any] | None = None,
        limit: int = 100,
        include_attachments: bool = True,
    ) -> list[dict[str, Any]]:
        """Retrieve emails via IMAP."""
        try:
            if not self._connection:
                self._connect()

            # Select folder
            self._connection.select(folder)

            # Search emails
            criteria = self._build_search_criteria(search_criteria)
            _, message_numbers = self._connection.search(None, *criteria)
            message_nums = message_numbers[0].split()[-limit:]

            emails = []
            for num in message_nums:
                _, msg_data = self._connection.fetch(num, "(RFC822)")
                email_body = msg_data[0][1]
                email_message = email.message_from_bytes(email_body)

                # Parse email data
                email_data = {
                    "id": num.decode(),
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

            return emails

        except imaplib.IMAP4.error as e:
            raise EmailFetchError(f"Failed to fetch IMAP messages: {str(e)}") from e
        except Exception as e:
            raise EmailConnectorError(
                f"Unexpected error fetching IMAP messages: {str(e)}"
            ) from e
        finally:
            self._disconnect()

    def test_credentials(self) -> bool:
        """Test IMAP credentials by connecting and listing folders."""
        try:
            self._connect()
            self._connection.list()
            return True
        except imaplib.IMAP4.error as e:
            raise EmailAuthenticationError(
                f"Failed to authenticate with IMAP server: {str(e)}"
            ) from e
        except Exception as e:
            raise EmailConnectorError(
                f"Unexpected error testing IMAP credentials: {str(e)}"
            ) from e
        finally:
            self._disconnect()
