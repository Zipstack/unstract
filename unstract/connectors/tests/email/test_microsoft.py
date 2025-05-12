"""Test cases for Microsoft email connector."""
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from O365.message import Message

from unstract.connectors.email.exceptions import (
    EmailAuthenticationError,
    EmailFetchError,
)
from unstract.connectors.email.microsoft.microsoft import UnstractMicrosoft



class TestMicrosoftConnector(unittest.TestCase):
    """Test cases for Microsoft email connector."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client_secrets = {
            "web": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "token_uri": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            }
        }
        self.settings = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
        }

    def test_initialization(self):
        """Test Microsoft connector initialization."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.return_value = json.dumps(self.mock_client_secrets)

        mock_account = MagicMock()
        mock_connection = MagicMock()
        with patch('unstract.connectors.email.microsoft.microsoft.GCSHelper', return_value=mock_gcs_helper), \
             patch('unstract.connectors.email.microsoft.microsoft.Account', return_value=mock_account), \
             patch('unstract.connectors.email.microsoft.microsoft.Connection', return_value=mock_connection):
            microsoft = UnstractMicrosoft(self.settings)
            self.assertEqual(microsoft.get_name(), "Microsoft Email")
            self.assertEqual(microsoft.requires_oauth(), True)
            self.assertEqual(
                microsoft.get_id(),
                "microsoft|d4a1c890-7b23-4c87-9f21-ac4812c6541b",
            )

    def test_initialization_failure(self):
        """Test Microsoft connector initialization failure."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.side_effect = Exception("Failed to get secret")

        mock_account = MagicMock()
        mock_connection = MagicMock()
        with patch('unstract.connectors.email.microsoft.microsoft.GCSHelper', return_value=mock_gcs_helper), \
             patch('unstract.connectors.email.microsoft.microsoft.Account', return_value=mock_account), \
             patch('unstract.connectors.email.microsoft.microsoft.Connection', return_value=mock_connection):
            with self.assertRaises(EmailAuthenticationError):
                UnstractMicrosoft(self.settings)

    def test_test_credentials_success(self):
        """Test successful credentials test."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.return_value = json.dumps(self.mock_client_secrets)

        mock_account = MagicMock()
        mock_account.mailbox().list_folders.return_value = iter([])
        mock_connection = MagicMock()
        with patch('unstract.connectors.email.microsoft.microsoft.GCSHelper', return_value=mock_gcs_helper), \
             patch('unstract.connectors.email.microsoft.microsoft.Account', return_value=mock_account), \
             patch('unstract.connectors.email.microsoft.microsoft.Connection', return_value=mock_connection):
            microsoft = UnstractMicrosoft(self.settings)
            self.assertTrue(microsoft.test_credentials())


    def test_test_credentials_failure(self):
        """Test credentials test failure."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.return_value = json.dumps(self.mock_client_secrets)

        mock_account = MagicMock()
        mock_account.mailbox().list_folders.side_effect = Exception("Authentication failed")
        mock_connection = MagicMock()
        with patch('unstract.connectors.email.microsoft.microsoft.GCSHelper', return_value=mock_gcs_helper), \
             patch('unstract.connectors.email.microsoft.microsoft.Account', return_value=mock_account), \
             patch('unstract.connectors.email.microsoft.microsoft.Connection', return_value=mock_connection):
            microsoft = UnstractMicrosoft(self.settings)
            with self.assertRaises(EmailAuthenticationError):
                microsoft.test_credentials()

    def test_get_emails_success(self):
        """Test successful email retrieval."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.return_value = json.dumps(self.mock_client_secrets)

        mock_account = MagicMock()
        mock_connection = MagicMock()
        with patch('unstract.connectors.email.microsoft.microsoft.GCSHelper', return_value=mock_gcs_helper), \
             patch('unstract.connectors.email.microsoft.microsoft.Account', return_value=mock_account), \
             patch('unstract.connectors.email.microsoft.microsoft.Connection', return_value=mock_connection):
            microsoft = UnstractMicrosoft(self.settings)
            # Rest of test setup

            # Mock message
            mock_message = MagicMock(spec=Message)
            mock_message.object_id = "msg1"
            mock_message.subject = "Test Subject"
            mock_message.sender = "sender@example.com"
            mock_message.to = ["recipient@example.com"]
            mock_message.received = datetime.now(timezone.utc)
            mock_message.body = "Test body\n"
            mock_message.has_attachments = False

            microsoft.account.mailbox().get_folder().get_messages.return_value = [
                mock_message
            ]

            emails = microsoft.get_emails(
                folder="Inbox",
                search_criteria={"subject": "test"},
                limit=1,
            )

            self.assertEqual(len(emails), 1)
            email = emails[0]
            self.assertEqual(email["subject"], "Test Subject")
            self.assertEqual(email["from"], "sender@example.com")
            self.assertEqual(email["to"], ["recipient@example.com"])
            self.assertIsInstance(email["date"], datetime)
            self.assertEqual(email["body"], "Test body\n")

    def test_get_emails_with_attachments(self):
        """Test email retrieval with attachments."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.return_value = json.dumps(self.mock_client_secrets)

        mock_account = MagicMock()
        mock_connection = MagicMock()
        with patch('unstract.connectors.email.microsoft.microsoft.GCSHelper', return_value=mock_gcs_helper), \
             patch('unstract.connectors.email.microsoft.microsoft.Account', return_value=mock_account), \
             patch('unstract.connectors.email.microsoft.microsoft.Connection', return_value=mock_connection):
            microsoft = UnstractMicrosoft(self.settings)
            # Rest of test setup

            # Mock message with attachment
            mock_message = MagicMock(spec=Message)
            mock_message.object_id = "msg1"
            mock_message.subject = "Test Subject"
            mock_message.sender.address = "sender@example.com"
            mock_message.to = [MagicMock(address="recipient@example.com")]
            mock_message.received = datetime.now(timezone.utc)
            mock_message.body = "Test body\n"
            mock_message.has_attachments = True

            # Mock attachment
            mock_attachment = MagicMock()
            mock_attachment.name = "test.txt"
            mock_attachment.content_type = "text/plain"
            mock_attachment.content = b"attachment content"
            mock_message.attachments = [mock_attachment]

            microsoft.account.mailbox().get_folder().get_messages.return_value = [
                mock_message
            ]

            emails = microsoft.get_emails(folder="Inbox", limit=1)

            self.assertEqual(len(emails), 1)
            email = emails[0]
            self.assertTrue("attachments" in email)
            self.assertEqual(len(email["attachments"]), 1)
            self.assertEqual(email["attachments"][0]["filename"], "test.txt")
            self.assertEqual(email["attachments"][0]["content_type"], "text/plain")
            self.assertEqual(
                email["attachments"][0]["content"], b"attachment content"
            )

    def test_get_emails_failure(self):
        """Test email retrieval failure."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.return_value = json.dumps(self.mock_client_secrets)

        mock_account = MagicMock()
        mock_account.mailbox().get_folder().get_messages.side_effect = Exception("Failed to fetch messages")
        mock_connection = MagicMock()
        with patch('unstract.connectors.email.microsoft.microsoft.GCSHelper', return_value=mock_gcs_helper), \
             patch('unstract.connectors.email.microsoft.microsoft.Account', return_value=mock_account), \
             patch('unstract.connectors.email.microsoft.microsoft.Connection', return_value=mock_connection):
            microsoft = UnstractMicrosoft(self.settings)
            with self.assertRaises(EmailFetchError):
                microsoft.get_emails()


if __name__ == "__main__":
    unittest.main()
