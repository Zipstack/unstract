"""Test cases for Gmail connector."""
import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

from unstract.connectors.email.exceptions import (
    EmailAuthenticationError,
    EmailFetchError,
)
from unstract.connectors.email.gmail.gmail import UnstractGmail



class TestGmailConnector(unittest.TestCase):
    """Test cases for Gmail connector."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client_secrets = {
            "web": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        self.settings = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
        }

    def test_initialization(self):
        """Test Gmail connector initialization."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.return_value = json.dumps(self.mock_client_secrets)

        with patch('unstract.connectors.email.gmail.gmail.GCSHelper', return_value=mock_gcs_helper):
            gmail = UnstractGmail(self.settings)
            self.assertEqual(gmail.get_name(), "Gmail")
            self.assertEqual(gmail.requires_oauth(), True)
            self.assertEqual(
                gmail.get_id(), "gmail|e4a1c890-7b23-4c87-9f21-ac4812c6541a"
            )

    def test_initialization_failure(self):
        """Test Gmail connector initialization failure."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.side_effect = Exception("Failed to get secret")

        with patch('unstract.connectors.email.gmail.gmail.GCSHelper', return_value=mock_gcs_helper):
            with self.assertRaises(EmailAuthenticationError):
                UnstractGmail(self.settings)

    def test_test_credentials_success(self):
        """Test successful credentials test."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.return_value = json.dumps(self.mock_client_secrets)

        with patch('unstract.connectors.email.gmail.gmail.GCSHelper', return_value=mock_gcs_helper):
            gmail = UnstractGmail(self.settings)
            gmail.service = MagicMock()
            gmail.service.users().labels().list().execute.return_value = {"labels": []}

            self.assertTrue(gmail.test_credentials())

    def test_test_credentials_failure(self):
        """Test credentials test failure."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.return_value = json.dumps(self.mock_client_secrets)

        with patch('unstract.connectors.email.gmail.gmail.GCSHelper', return_value=mock_gcs_helper):
            gmail = UnstractGmail(self.settings)
            gmail.service = MagicMock()
            gmail.service.users().labels().list.side_effect = HttpError(
                resp=MagicMock(status=401), content=b"Unauthorized"
            )

            with self.assertRaises(EmailAuthenticationError):
                gmail.test_credentials()

    def test_get_emails_success(self):
        """Test successful email retrieval."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.return_value = json.dumps(self.mock_client_secrets)

        with patch('unstract.connectors.email.gmail.gmail.GCSHelper', return_value=mock_gcs_helper):
            gmail = UnstractGmail(self.settings)
            gmail.service = MagicMock()

            # Mock message list response
            gmail.service.users().messages().list().execute.return_value = {
                "messages": [{"id": "msg1"}]
            }

            # Mock message get response
            message = {
                "id": "msg1",
                "internalDate": "1616579400000",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Test Subject"},
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "To", "value": "recipient@example.com"},
                    ],
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": "Test body\n"},
                        }
                    ],
                },
            }
            gmail.service.users().messages().get().execute.return_value = message

            emails = gmail.get_emails(
                folder="INBOX",
                search_criteria={"subject": "test"},
                limit=1,
            )

            self.assertEqual(len(emails), 1)
            email = emails[0]
            self.assertEqual(email["subject"], "Test Subject")
            self.assertEqual(email["from"], "sender@example.com")
            self.assertEqual(email["to"], ["recipient@example.com"])
            self.assertIsInstance(email["date"], datetime)

    def test_get_emails_with_attachments(self):
        """Test email retrieval with attachments."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.return_value = json.dumps(self.mock_client_secrets)

        with patch('unstract.connectors.email.gmail.gmail.GCSHelper', return_value=mock_gcs_helper):
            gmail = UnstractGmail(self.settings)
            gmail.service = MagicMock()

            # Mock message list response
            gmail.service.users().messages().list().execute.return_value = {
                "messages": [{"id": "msg1"}]
            }

            # Mock message get response with attachment
            message = {
                "id": "msg1",
                "internalDate": "1616579400000",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Test Subject"},
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "To", "value": "recipient@example.com"},
                    ],
                    "parts": [
                        {
                            "filename": "test.txt",
                            "mimeType": "text/plain",
                            "body": {
                                "attachmentId": "att1",
                                "size": 100,
                            },
                        }
                    ],
                },
            }
            gmail.service.users().messages().get().execute.return_value = message
            gmail.service.users().messages().attachments().get().execute.return_value = {
                "data": "attachment content"
            }

            emails = gmail.get_emails(folder="INBOX", limit=1)

            self.assertEqual(len(emails), 1)
            email = emails[0]
            self.assertTrue("attachments" in email)
            self.assertEqual(len(email["attachments"]), 1)
            self.assertEqual(email["attachments"][0]["filename"], "test.txt")
            self.assertEqual(email["attachments"][0]["content_type"], "text/plain")
            self.assertEqual(email["attachments"][0]["size"], 100)

    def test_get_emails_failure(self):
        """Test email retrieval failure."""
        mock_gcs_helper = MagicMock()
        mock_gcs_helper.get_secret.return_value = json.dumps(self.mock_client_secrets)

        with patch('unstract.connectors.email.gmail.gmail.GCSHelper', return_value=mock_gcs_helper):
            gmail = UnstractGmail(self.settings)
            gmail.service = MagicMock()
            gmail.service.users().messages().list.side_effect = HttpError(
                resp=MagicMock(status=500), content=b"Server error"
            )

            with self.assertRaises(EmailFetchError):
                gmail.get_emails()


if __name__ == "__main__":
    unittest.main()
