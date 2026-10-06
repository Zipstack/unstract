"""WorkerConfig reports a missing Celery broker only when the log transport needs it.

On the Redis log transport a deployment may run with no broker at all, so flagging
it there would be a false configuration error on every worker start. The Celery
transport still reports it, exactly as before.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from shared.infrastructure.config.worker_config import WorkerConfig

_BASE_ENV = {
    "INTERNAL_API_BASE_URL": "http://test-backend:8000/internal",
    "INTERNAL_SERVICE_API_KEY": "test-key-123",
    "DB_HOST": "localhost",
    "DB_USER": "test",
    "DB_PASSWORD": "test",
    "DB_NAME": "testdb",
}
_BROKER_ENV = {
    "CELERY_BROKER_BASE_URL": "amqp://localhost:5672//",
    "CELERY_BROKER_USER": "guest",
    "CELERY_BROKER_PASS": "guest",
}
_BROKER_ERROR = "CELERY_BROKER_URL could not be built"


def _validate(env: dict[str, str]) -> tuple[WorkerConfig, str]:
    """Build a config under ``env`` and return it with its validation error text."""
    with patch.dict("os.environ", env, clear=True):
        config = WorkerConfig()
        try:
            config.validate()
        except ValueError as exc:
            return config, str(exc)
        return config, ""


def test_redis_transport_without_a_broker_is_valid():
    config, error = _validate({**_BASE_ENV, "LOG_TRANSPORT": "redis"})
    assert config.celery_broker_url == ""
    assert _BROKER_ERROR not in error


@pytest.mark.parametrize("transport", [None, "celery"])
def test_celery_transport_without_a_broker_is_reported(transport):
    env = dict(_BASE_ENV)
    if transport is not None:
        env["LOG_TRANSPORT"] = transport
    _, error = _validate(env)
    assert _BROKER_ERROR in error


@pytest.mark.parametrize("transport", ["redis", "celery"])
def test_a_configured_broker_is_valid_on_either_transport(transport):
    config, error = _validate({**_BASE_ENV, **_BROKER_ENV, "LOG_TRANSPORT": transport})
    assert config.celery_broker_url == "amqp://guest:guest@localhost:5672//"
    assert _BROKER_ERROR not in error
