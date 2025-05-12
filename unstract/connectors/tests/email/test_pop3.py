"""Test cases for POP3 email connector."""
import email
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import poplib

from unstract.connectors.email.exceptions import (
    EmailAuthenticationError,
    EmailFetchError,
)
from unstract.connectors.email.pop3.pop3 import UnstractPOP3


class TestPOP3Connector(unittest.TestCase):
    """Test cases for POP3 email connector."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = {
            "host": "pop3.example.com",
            "port": 995,
            "username": "test@example.com",
            "password": "test_password",
            "use_ssl": True,
        }

    def test_initialization(self):
        """Test POP3 connector initialization."""
        pop3 = UnstractPOP3(self.settings)
        self.assertEqual(pop3.get_name(), "POP3 Email")
        self.assertEqual(pop3.requires_oauth(), False)
        self.assertEqual(
            pop3.get_id(), "pop3|a3b1d681-9c8b-4f6b-b972-1a6a095312f5"
        )

    @patch("poplib.POP3_SSL")
    def test_test_credentials_success(self, mock_pop3_ssl):
        """Test successful credentials test."""
        mock_connection = MagicMock()
        mock_pop3_ssl.return_value = mock_connection

        pop3 = UnstractPOP3(self.settings)
        self.assertTrue(pop3.test_credentials())

        mock_connection.user.assert_called_once_with(self.settings["username"])
        mock_connection.pass_.assert_called_once_with(self.settings["password"])
        mock_connection.quit.assert_called_once()

    @patch("poplib.POP3_SSL")
    def test_test_credentials_failure(self, mock_pop3_ssl):
        """Test credentials test failure."""
        mock_connection = MagicMock()
        mock_connection.user.side_effect = poplib.error_proto(
            "Invalid credentials"
        )
        mock_pop3_ssl.return_value = mock_connection

        pop3 = UnstractPOP3(self.settings)
        with self.assertRaises(EmailAuthenticationError):
            pop3.test_credentials()

    @patch("poplib.POP3_SSL")
    def test_get_emails_success(self, mock_pop3_ssl):
        """Test successful email retrieval."""
        mock_connection = MagicMock()
        mock_pop3_ssl.return_value = mock_connection

        # Mock email message
        email_date = "Wed, 19 Mar 2025 06:22:41 +0000"
        msg = email.message.EmailMessage()
        msg["Subject"] = "Test Subject"
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Date"] = email_date
        msg.set_content("Test body")

        mock_connection.list.return_value = (None, [b"1 1000"], None)
        mock_connection.retr.return_value = (
            None,
            [line.encode() for line in msg.as_string().split("\n")],
            None,
        )

        pop3 = UnstractPOP3(self.settings)
        emails = pop3.get_emails(limit=1)

        self.assertEqual(len(emails), 1)
        email_data = emails[0]
        self.assertEqual(email_data["subject"], "Test Subject")
        self.assertEqual(email_data["from"], "sender@example.com")
        self.assertEqual(email_data["to"], ["recipient@example.com"])
        self.assertIsInstance(email_data["date"], datetime)
        self.assertEqual(email_data["body"], "Test body\n")

    @patch("poplib.POP3_SSL")
    def test_get_emails_with_attachments(self, mock_pop3_ssl):
        """Test email retrieval with attachments."""
        mock_connection = MagicMock()
        mock_pop3_ssl.return_value = mock_connection

        # Create multipart message with attachment
        msg = email.mime.multipart.MIMEMultipart()
        msg["Subject"] = "Test Subject"
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Date"] = "Wed, 19 Mar 2025 06:22:41 +0000"

        # Add text part
        text_part = email.mime.text.MIMEText("Test body", "plain")
        msg.attach(text_part)

        # Add attachment
        attachment = email.mime.base.MIMEBase("text", "plain")
        attachment.set_payload(b"attachment content")
        email.encoders.encode_base64(attachment)
        attachment.add_header(
            "Content-Disposition", "attachment", filename="test.txt"
        )
        msg.attach(attachment)

        mock_connection.list.return_value = (None, [b"1 1000"], None)
        mock_connection.retr.return_value = (
            None,
            [line.encode() for line in msg.as_string().split("\n")],
            None,
        )

        pop3 = UnstractPOP3(self.settings)
        emails = pop3.get_emails(limit=1)

        self.assertEqual(len(emails), 1)
        email_data = emails[0]
        self.assertTrue("attachments" in email_data)
        self.assertEqual(len(email_data["attachments"]), 1)
        self.assertEqual(email_data["attachments"][0]["filename"], "test.txt")
        self.assertEqual(
            email_data["attachments"][0]["content_type"], "text/plain"
        )

    @patch("poplib.POP3_SSL")
    def test_get_emails_failure(self, mock_pop3_ssl):
        """Test email retrieval failure."""
        mock_connection = MagicMock()
        mock_connection.list.side_effect = poplib.error_proto(
            "Failed to list messages"
        )
        mock_pop3_ssl.return_value = mock_connection

        pop3 = UnstractPOP3(self.settings)
        with self.assertRaises(EmailFetchError):
            pop3.get_emails()


if __name__ == "__main__":
    unittest.main()
