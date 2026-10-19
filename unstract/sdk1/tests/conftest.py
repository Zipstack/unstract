"""Pytest configuration and fixtures for unstract-sdk1 tests."""

import os

# Pin LiteLLM to the model registry bundled with the pinned wheel, before
# anything imports litellm. Left unset, litellm fetches its registry over the
# network at import time, which makes any test that depends on it (notably the
# AWS Bedrock Mantle routing tests, whose whole subject is registry membership)
# both non-hermetic and dependent on which test module happened to import
# litellm first. This has to be a module-scope assignment in conftest rather
# than a fixture: the variable is read once at litellm import, which happens at
# collection time, long before any fixture body runs.
#
# `setdefault` so an operator can still opt into the live registry -- e.g. to
# find out early that AWS shipped a Mantle model the pinned wheel predates --
# with LITELLM_LOCAL_MODEL_COST_MAP=False.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import logging  # noqa: E402
from collections.abc import Callable  # noqa: E402
from typing import Any  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402
from _pytest.monkeypatch import MonkeyPatch  # noqa: E402


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
        "PLATFORM_SERVICE_BASE_DELAY",
        "PLATFORM_SERVICE_MULTIPLIER",
        "PLATFORM_SERVICE_JITTER",
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
