"""The sidecar must inherit the log transport (UN-3755).

``_get_sidecar_container_config`` builds the sidecar's environment as a hand-picked
**allowlist**, not inherited env. So a variable the sidecar needs but that nobody added
here is silently absent at runtime — no error, no warning.

That matters for ``LOG_TRANSPORT`` specifically: the sidecar is a ``LogPublisher``
producer (``tool_sidecar/log_processor.py:165``), and ``LogPublisher`` defaults to the
Celery/RabbitMQ transport when the variable is unset. Miss it and tool logs keep going
to ``celery_log_task_queue`` while every other publisher moves to Redis — and once the
Celery log consumer is scaled to zero those logs are simply dropped, with live
streaming and ``execution_log`` rows both silently missing for container-based tools.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from unstract.runner.constants import Env
from unstract.runner.runner import UnstractRunner


@pytest.fixture
def sidecar_env(monkeypatch):
    """Build a sidecar env dict with the client mocked out."""

    def _build(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        runner = UnstractRunner.__new__(UnstractRunner)
        runner.client = MagicMock()
        runner.client.get_container_run_config.side_effect = (
            lambda **kwargs: kwargs  # return the call kwargs so we can read `envs`
        )
        config = runner._get_sidecar_container_config(
            container_name="c",
            shared_log_dir="/d",
            shared_log_file="/d/log",
            organization_id="org",
            execution_id="exec",
            file_execution_id="fe",
            messaging_channel="chan",
            tool_instance_id="ti",
        )
        return config["envs"]

    return _build


class TestSidecarLogTransport:
    def test_defaults_to_celery_when_unset(self, sidecar_env, monkeypatch):
        monkeypatch.delenv(Env.LOG_TRANSPORT, raising=False)
        envs = sidecar_env()
        # Present and explicit, not merely absent — the sidecar's LogPublisher reads
        # this key, and an explicit default documents the flag-off state.
        assert envs[Env.LOG_TRANSPORT] == "celery"

    def test_forwards_redis_transport_to_the_sidecar(self, sidecar_env):
        envs = sidecar_env(LOG_TRANSPORT="redis")
        assert envs[Env.LOG_TRANSPORT] == "redis"

    def test_forwards_the_stream_queue_name(self, sidecar_env):
        # If a deployment renames the queue, the sidecar must push to the same list
        # the consumer drains, or its logs land somewhere nobody reads.
        envs = sidecar_env(LOG_TRANSPORT="redis", LOG_STREAM_QUEUE_NAME="custom_stream")
        assert envs[Env.LOG_STREAM_QUEUE_NAME] == "custom_stream"

    def test_redis_credentials_are_already_present(self, sidecar_env):
        """The Redis transport needs no NEW credential in this allowlist.

        This is the concrete payoff of choosing a Redis list over the PG queue for the
        log hop: REDIS_* is already forwarded, whereas PG would have required adding
        database credentials to every spawned sidecar.
        """
        envs = sidecar_env(LOG_TRANSPORT="redis", REDIS_HOST="r", REDIS_PORT="6379")
        assert envs["REDIS_HOST"] == "r"
        assert envs["REDIS_PORT"] == "6379"

    def test_celery_broker_still_forwarded_for_the_flag_off_path(self, sidecar_env):
        # Flag-off must stay intact: the sidecar still publishes over AMQP.
        envs = sidecar_env(CELERY_BROKER_BASE_URL="amqp://x")
        assert envs["CELERY_BROKER_BASE_URL"] == "amqp://x"
