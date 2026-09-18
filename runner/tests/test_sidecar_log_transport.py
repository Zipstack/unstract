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


class TestSidecarRedisTls:
    """TLS settings must reach the sidecar too (UN-4123).

    Same allowlist trap as ``LOG_TRANSPORT`` above, one layer deeper: the sidecar
    builds its OWN Redis client, so when the platform moves to a TLS endpoint a
    sidecar that never learned about it keeps dialling plaintext. The failure is a
    connection error at best; at worst it reaches a different db and tool logs go
    missing with everything else looking healthy.
    """

    def test_tls_settings_are_forwarded(self, sidecar_env):
        envs = sidecar_env(
            REDIS_SSL="true",
            REDIS_SSL_CERT_REQS="required",
            REDIS_SSL_CA_CERTS="/etc/ssl/redis-ca.pem",
        )
        assert envs[Env.REDIS_SSL] == "true"
        assert envs[Env.REDIS_SSL_CERT_REQS] == "required"
        assert envs[Env.REDIS_SSL_CA_CERTS] == "/etc/ssl/redis-ca.pem"

    def test_db_is_forwarded(self, sidecar_env):
        """Without this the sidecar sits on db 0 while everyone else honours REDIS_DB.

        Nothing errors: it simply publishes into a keyspace no consumer drains.
        """
        envs = sidecar_env(REDIS_DB="3")
        assert envs[Env.REDIS_DB] == "3"

    def test_url_is_forwarded(self, sidecar_env):
        envs = sidecar_env(REDIS_URL="rediss://cache.example:6380/2")
        assert envs[Env.REDIS_URL] == "rediss://cache.example:6380/2"

    def test_unset_values_are_omitted_entirely(self, sidecar_env, monkeypatch):
        """An empty string is NOT the same as absent.

        ``os.getenv(key, fallback)`` returns "" for a key that exists but is empty,
        which suppresses the fallback — so forwarding blanks would turn "inherit the
        default" into "explicitly configured as nothing".
        """
        for key in (
            Env.REDIS_SSL,
            Env.REDIS_SSL_CERT_REQS,
            Env.REDIS_SSL_CA_CERTS,
            Env.REDIS_DB,
            Env.REDIS_URL,
        ):
            monkeypatch.delenv(key, raising=False)
        envs = sidecar_env()
        for key in (
            Env.REDIS_SSL,
            Env.REDIS_SSL_CERT_REQS,
            Env.REDIS_SSL_CA_CERTS,
            Env.REDIS_DB,
            Env.REDIS_URL,
        ):
            assert key not in envs

    def test_plaintext_deployment_is_unchanged(self, sidecar_env, monkeypatch):
        """The whole point: no TLS configured means the sidecar env is as it was."""
        monkeypatch.delenv(Env.REDIS_SSL, raising=False)
        envs = sidecar_env(REDIS_HOST="r", REDIS_PORT="6379")
        assert envs["REDIS_HOST"] == "r"
        assert Env.REDIS_SSL not in envs
