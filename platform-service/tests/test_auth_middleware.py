"""Tests for bearer token validation used by `authentication_middleware`."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from flask import Flask
from unstract.platform_service.controller import platform

# Platform keys are UUIDs (the key column is a UUID field).
TOKEN = str(uuid.UUID(int=1))


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
    _mock_safe_cursor(monkeypatch, ("id", TOKEN, True))
    assert platform.validate_bearer_token(TOKEN) is True


def test_rejects_missing_token(app_ctx: None) -> None:
    assert platform.validate_bearer_token(None) is False


def test_rejects_unknown_token(app_ctx: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_safe_cursor(monkeypatch, None)
    assert platform.validate_bearer_token(TOKEN) is False


def test_rejects_inactive_token(app_ctx: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_safe_cursor(monkeypatch, ("id", TOKEN, False))
    assert platform.validate_bearer_token(TOKEN) is False


def test_db_error_denies_access(app_ctx: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth must fail closed when the token lookup blows up."""

    # Raising on call suffices: `safe_cursor(...)` is invoked inside the try.
    def _boom(query: str, params: tuple = ()) -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(platform, "safe_cursor", _boom)
    assert platform.validate_bearer_token(TOKEN) is False


SECRET_TOKEN = str(uuid.UUID(hex="abcd" + "1" * 28))


@pytest.mark.parametrize(
    "result_row",
    [None, ("id", SECRET_TOKEN, False), ("id", "some-other-key", True)],
    ids=["unknown", "inactive", "mismatched"],
)
def test_rejection_logs_only_a_token_prefix(
    app_ctx: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    result_row: Any,
) -> None:
    _mock_safe_cursor(monkeypatch, result_row)

    with caplog.at_level("ERROR"):
        assert platform.validate_bearer_token(SECRET_TOKEN) is False

    assert "abcd..." in caplog.text
    assert SECRET_TOKEN not in caplog.text


def test_malformed_token_is_rejected_before_the_query(
    app_ctx: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-UUID token would make Postgres quote it back in a logged error."""
    malformed = SECRET_TOKEN + "x"

    queries: list[tuple] = []
    _mock_safe_cursor(monkeypatch, None)
    recording_cursor = platform.safe_cursor

    def _recording(query: str, params: tuple = ()) -> Any:
        queries.append(params)
        return recording_cursor(query, params)

    monkeypatch.setattr(platform, "safe_cursor", _recording)

    with caplog.at_level("ERROR"):
        assert platform.validate_bearer_token(malformed) is False

    assert queries == []
    assert "Malformed bearer token" in caplog.text
    assert "abcd" not in caplog.text
