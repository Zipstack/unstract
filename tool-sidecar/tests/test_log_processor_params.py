"""The sidecar's startup check must only demand what its log transport uses.

The Celery broker is needed only when logs are published over AMQP. On the Redis
transport a deployment with no broker at all must still start the sidecar, while the
Celery transport (the default) keeps failing fast on a missing broker as before.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from unstract.tool_sidecar import log_processor
from unstract.tool_sidecar.constants import Env

_BASE_ENV = {
    Env.TOOL_INSTANCE_ID: "ti",
    Env.EXECUTION_ID: "exec",
    Env.ORGANIZATION_ID: "org",
    Env.FILE_EXECUTION_ID: "fe",
    Env.MESSAGING_CHANNEL: "chan",
    Env.LOG_PATH: "/shared/logs/logs.txt",
    Env.REDIS_HOST: "redis",
    Env.REDIS_PORT: "6379",
}
_BROKER_ENV = {
    Env.CELERY_BROKER_BASE_URL: "amqp://rabbit:5672//",
    Env.CELERY_BROKER_USER: "user",
    Env.CELERY_BROKER_PASS: "pass",
}


@pytest.fixture
def processor():
    """Stop ``main`` at the point it would start tailing the log file."""
    with patch.object(log_processor, "LogProcessor") as cls, patch(
        "signal.signal"
    ):
        yield cls


def _set_env(monkeypatch, transport: str | None, broker: bool) -> None:
    for key in (*_BASE_ENV, *_BROKER_ENV, "LOG_TRANSPORT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    if broker:
        for key, value in _BROKER_ENV.items():
            monkeypatch.setenv(key, value)
    if transport is not None:
        monkeypatch.setenv("LOG_TRANSPORT", transport)


def test_redis_transport_starts_without_a_broker(monkeypatch, processor):
    _set_env(monkeypatch, transport="redis", broker=False)
    log_processor.main()
    processor.return_value.monitor_logs.assert_called_once()


@pytest.mark.parametrize("transport", ["celery", None])
@pytest.mark.parametrize("missing", list(_BROKER_ENV))
def test_celery_transport_still_requires_each_broker_setting(
    monkeypatch, processor, transport, missing
):
    _set_env(monkeypatch, transport=transport, broker=True)
    monkeypatch.delenv(missing)
    with pytest.raises(ValueError) as excinfo:
        log_processor.main()
    assert missing in str(excinfo.value)
    for present in set(_BROKER_ENV) - {missing}:
        assert present not in str(excinfo.value)
    processor.assert_not_called()


def test_celery_transport_starts_with_the_broker(monkeypatch, processor):
    _set_env(monkeypatch, transport="celery", broker=True)
    log_processor.main()
    processor.return_value.monitor_logs.assert_called_once()
