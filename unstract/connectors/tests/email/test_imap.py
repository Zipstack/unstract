"""Test cases for IMAP email connector."""
import email
import unittest
from datetime import datetime
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch

import imaplib

from unstract.connectors.email.exceptions import (
    EmailAuthenticationError,
    EmailFetchError,
)
from unstract.connectors.email.imap.imap import UnstractIMAP


class TestIMAPConnector(unittest.TestCase):
    """Test cases for IMAP email connector."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = {
            "host": "imap.example.com",
            "port": 993,
            "username": "test@example.com",
            "password": "test_password",
            "use_ssl": True,
        }

    def test_initialization(self):
        """Test IMAP connector initialization."""
        imap = UnstractIMAP(self.settings)
        self.assertEqual(imap.get_name(), "IMAP Email")
        self.assertEqual(imap.requires_oauth(), False)
        self.assertEqual(
            imap.get_id(), "imap|f2b1d681-9c8b-4f6b-b972-1a6a095312f4"
        )

    @patch("imaplib.IMAP4_SSL")
    def test_test_credentials_success(self, mock_imap_ssl):
        """Test successful credentials test."""
        mock_connection = MagicMock()
        mock_imap_ssl.return_value = mock_connection

        imap = UnstractIMAP(self.settings)
        self.assertTrue(imap.test_credentials())

        mock_connection.login.assert_called_once_with(
            self.settings["username"], self.settings["password"]
        )
        mock_connection.list.assert_called_once()
        mock_connection.logout.assert_called_once()

    @patch("imaplib.IMAP4_SSL")
    def test_test_credentials_failure(self, mock_imap_ssl):
        """Test credentials test failure."""
        mock_connection = MagicMock()
        mock_connection.login.side_effect = imaplib.IMAP4.error(
            "Invalid credentials"
        )
        mock_imap_ssl.return_value = mock_connection

        imap = UnstractIMAP(self.settings)
        with self.assertRaises(EmailAuthenticationError):
            imap.test_credentials()

    @patch("imaplib.IMAP4_SSL")
    def test_get_emails_success(self, mock_imap_ssl):
        """Test successful email retrieval."""
        mock_connection = MagicMock()
        mock_imap_ssl.return_value = mock_connection

        # Mock email message
        email_date = "Wed, 19 Mar 2025 06:22:41 +0000"
        msg = email.message.EmailMessage()
        msg["Subject"] = "Test Subject"
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Date"] = email_date
        msg.set_content("Test body")

        mock_connection.search.return_value = (None, [b"1"])
        mock_connection.fetch.return_value = (
            None,
            [(b"1", msg.as_bytes())],
        )

        imap = UnstractIMAP(self.settings)
        emails = imap.get_emails(
            folder="INBOX",
            search_criteria={"subject": "test"},
            limit=1,
        )

        self.assertEqual(len(emails), 1)
        email_data = emails[0]
        self.assertEqual(email_data["subject"], "Test Subject")
        self.assertEqual(email_data["from"], "sender@example.com")
        self.assertEqual(email_data["to"], ["recipient@example.com"])
        self.assertIsInstance(email_data["date"], datetime)
        self.assertEqual(email_data["body"], "Test body\n")

    @patch("imaplib.IMAP4_SSL")
    def test_get_emails_with_attachments(self, mock_imap_ssl):
        """Test email retrieval with attachments."""
        mock_connection = MagicMock()
        mock_imap_ssl.return_value = mock_connection

        # Create multipart message with attachment
        msg = MIMEMultipart()
        msg["Subject"] = "Test Subject"
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Date"] = "Wed, 19 Mar 2025 06:22:41 +0000"

        # Add text part
        text_part = MIMEText("Test body", "plain")
        msg.attach(text_part)

        # Add attachment
        attachment = MIMEBase("text", "plain")
        attachment.set_payload(b"attachment content")
        email.encoders.encode_base64(attachment)
        attachment.add_header(
            "Content-Disposition", "attachment", filename="test.txt"
        )
        msg.attach(attachment)

        mock_connection.search.return_value = (None, [b"1"])
        mock_connection.fetch.return_value = (
            None,
            [(b"1", msg.as_bytes())],
        )

        imap = UnstractIMAP(self.settings)
        emails = imap.get_emails(folder="INBOX", limit=1)

        self.assertEqual(len(emails), 1)
        email_data = emails[0]
        self.assertTrue("attachments" in email_data)
        self.assertEqual(len(email_data["attachments"]), 1)
        self.assertEqual(email_data["attachments"][0]["filename"], "test.txt")
        self.assertEqual(
            email_data["attachments"][0]["content_type"], "text/plain"
        )

    @patch("imaplib.IMAP4_SSL")
    def test_get_emails_failure(self, mock_imap_ssl):
        """Test email retrieval failure."""
        mock_connection = MagicMock()
        mock_connection.select.side_effect = imaplib.IMAP4.error(
            "Failed to select folder"
        )
        mock_imap_ssl.return_value = mock_connection

        imap = UnstractIMAP(self.settings)
        with self.assertRaises(EmailFetchError):
            imap.get_emails()

    def test_build_search_criteria(self):
        """Test search criteria building."""
        imap = UnstractIMAP(self.settings)
        criteria = imap._build_search_criteria(
            {
                "from": "sender@example.com",
                "to": "recipient@example.com",
                "subject": "test",
                "after": datetime(2025, 3, 19),
                "before": datetime(2025, 3, 20),
            }
        )

        self.assertIn("FROM", criteria)
        self.assertIn("sender@example.com", criteria)
        self.assertIn("TO", criteria)
        self.assertIn("recipient@example.com", criteria)
        self.assertIn("SUBJECT", criteria)
        self.assertIn("test", criteria)
        self.assertIn("SINCE", criteria)
        self.assertIn("19-Mar-2025", criteria)
        self.assertIn("BEFORE", criteria)
        self.assertIn("20-Mar-2025", criteria)


if __name__ == "__main__":
    unittest.main()
