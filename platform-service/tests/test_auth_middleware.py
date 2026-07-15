"""Tests for bearer token validation used by `authentication_middleware`."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from flask import Flask
from unstract.platform_service.controller import platform


@pytest.fixture
def app_ctx() -> Iterator[None]:
    """`validate_bearer_token` logs via `flask.current_app`."""
    with Flask(__name__).app_context():
        yield


def _mock_safe_cursor(monkeypatch: pytest.MonkeyPatch, result_row: Any) -> None:
    class _Cursor:
        def fetchone(self) -> Any:
            return result_row

    @contextmanager
    def _safe_cursor(query: str, params: tuple = ()) -> Iterator[_Cursor]:
        yield _Cursor()

    monkeypatch.setattr(platform, "safe_cursor", _safe_cursor)


def test_valid_active_token(app_ctx: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_safe_cursor(monkeypatch, ("id", "test-token", True))
    assert platform.validate_bearer_token("test-token") is True


def test_rejects_missing_token(app_ctx: None) -> None:
    assert platform.validate_bearer_token(None) is False


def test_rejects_unknown_token(app_ctx: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_safe_cursor(monkeypatch, None)
    assert platform.validate_bearer_token("test-token") is False


def test_rejects_inactive_token(app_ctx: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_safe_cursor(monkeypatch, ("id", "test-token", False))
    assert platform.validate_bearer_token("test-token") is False


def test_db_error_denies_access(app_ctx: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth must fail closed when the token lookup blows up."""

    # Raising on call suffices: `safe_cursor(...)` is invoked inside the try.
    def _boom(query: str, params: tuple = ()) -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(platform, "safe_cursor", _boom)
    assert platform.validate_bearer_token("test-token") is False
