"""Pytest configuration and fixtures for unstract-sdk1 tests."""

import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create a mock logger for testing."""
    logger = MagicMock(spec=logging.Logger)
    return logger


@pytest.fixture
def clean_env(monkeypatch: MonkeyPatch) -> MonkeyPatch:
    """Clean environment variables before each test."""
    # Remove any retry-related environment variables
    env_vars = [
        "PLATFORM_SERVICE_MAX_RETRIES",
        "PLATFORM_SERVICE_MAX_TIME",
        "PLATFORM_SERVICE_BASE_DELAY",
        "PLATFORM_SERVICE_MULTIPLIER",
        "PLATFORM_SERVICE_JITTER",
        "PROMPT_SERVICE_MAX_RETRIES",
        "PROMPT_SERVICE_MAX_TIME",
        "PROMPT_SERVICE_BASE_DELAY",
        "PROMPT_SERVICE_MULTIPLIER",
        "PROMPT_SERVICE_JITTER",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def set_env(monkeypatch: MonkeyPatch) -> Callable[..., None]:
    """Helper fixture to set environment variables."""

    def _set_env(prefix: str, **kwargs: Any) -> None:  # noqa: ANN401
        """Set environment variables with given prefix.

        Args:
            prefix: Environment variable prefix (e.g., 'PLATFORM_SERVICE')
            **kwargs: Key-value pairs to set (e.g., max_retries=5)
        """
        for key, value in kwargs.items():
            env_key = f"{prefix}_{key.upper()}"
            monkeypatch.setenv(env_key, str(value))

    return _set_env
