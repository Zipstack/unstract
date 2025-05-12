"""Shared test fixtures for email connector tests."""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_gcs_helper(mocker):
    """Mock GCSHelper for testing."""
    mock = mocker.patch("unstract.connectors.gcs_helper.GCSHelper")
    mock_instance = MagicMock()
    mock.return_value = mock_instance
    return mock_instance


@pytest.fixture
def mock_gmail_client_secrets():
    """Gmail client secrets for testing."""
    return {
        "web": {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


@pytest.fixture
def mock_microsoft_client_secrets():
    """Microsoft client secrets for testing."""
    return {
        "web": {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "token_uri": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        }
    }


@pytest.fixture
def mock_imap_settings():
    """IMAP settings for testing."""
    return {
        "host": "imap.example.com",
        "port": 993,
        "username": "test@example.com",
        "password": "test_password",
        "use_ssl": True,
    }


@pytest.fixture
def mock_pop3_settings():
    """POP3 settings for testing."""
    return {
        "host": "pop3.example.com",
        "port": 995,
        "username": "test@example.com",
        "password": "test_password",
        "use_ssl": True,
    }
