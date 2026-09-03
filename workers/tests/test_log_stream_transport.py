"""Tests for the log-streaming transport branch (UN-3755).

``LogPublisher.publish`` is the hop that lets the log consumer stop being a Celery
worker. What matters is that the flag-off path is untouched (it is what staging and
production run), that the flag-on envelope carries the task **name** so the consumer can
dispatch it, and that a logging fault can never break an execution.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from unstract.core.constants import LogProcessingTask
from unstract.core.pubsub_helper import LogPublisher

_PAYLOAD = {"type": "LOG", "level": "INFO", "log": "hello", "timestamp": 1.0}


@pytest.fixture
def redis_client():
    client = MagicMock()
    client.llen.return_value = 0
    with patch.object(LogPublisher, "_get_redis_client", return_value=client):
        yield client


@pytest.fixture
def kombu():
    with patch.object(LogPublisher, "kombu_conn") as conn:
        yield conn.Producer.return_value.__enter__.return_value


class TestFlagOff:
    """Default transport must remain exactly what it is on main."""

    def test_publishes_to_amqp_and_never_touches_the_redis_stream(
        self, monkeypatch, kombu, redis_client
    ):
        monkeypatch.delenv("LOG_TRANSPORT", raising=False)
        assert LogPublisher.publish("chan-1", _PAYLOAD) is True

        kombu.publish.assert_called_once()
        kwargs = kombu.publish.call_args.kwargs
        assert kwargs["routing_key"] == LogProcessingTask.QUEUE_NAME
        assert kwargs["headers"] == {"task": LogProcessingTask.TASK_NAME}
        redis_client.rpush.assert_not_called()

    def test_an_unrelated_transport_value_still_uses_celery(
        self, monkeypatch, kombu, redis_client
    ):
        # Fail closed: only the exact opt-in switches transport.
        monkeypatch.setenv("LOG_TRANSPORT", "rabbit")
        LogPublisher.publish("chan-1", _PAYLOAD)
        kombu.publish.assert_called_once()
        redis_client.rpush.assert_not_called()


class TestFlagOn:
    @pytest.fixture(autouse=True)
    def _enable(self, monkeypatch):
        monkeypatch.setenv("LOG_TRANSPORT", "redis")
        monkeypatch.setenv("LOG_STREAM_QUEUE_NAME", "log_stream_queue")

    def test_pushes_an_envelope_and_never_touches_amqp(self, kombu, redis_client):
        assert LogPublisher.publish("chan-1", _PAYLOAD) is True
        kombu.publish.assert_not_called()

        queue, raw = redis_client.rpush.call_args[0]
        assert queue == "log_stream_queue"
        envelope = json.loads(raw)
        # The task name is what the consumer dispatches on. Without it a rename would
        # silently drop every log with nothing at the publish site to trace it from.
        assert envelope["task"] == LogProcessingTask.TASK_NAME
        assert envelope["kwargs"]["message"] == _PAYLOAD
        assert envelope["kwargs"]["user_session_id"] == "chan-1"
        assert envelope["kwargs"]["event"] == "logs:chan-1"

    def test_drops_at_capacity_rather_than_growing_until_redis_ooms(self, redis_client):
        redis_client.llen.return_value = 10_000
        assert LogPublisher.publish("chan-1", _PAYLOAD) is True
        redis_client.rpush.assert_not_called()

    def test_a_redis_failure_is_swallowed_not_raised(self, redis_client):
        # A logging fault must never surface into the execution that emitted it.
        redis_client.rpush.side_effect = RuntimeError("redis down")
        assert LogPublisher.publish("chan-1", _PAYLOAD) is False

    def test_unified_notification_still_stored(self, redis_client):
        with patch.object(LogPublisher, "store_for_unified_notification") as store:
            LogPublisher.publish("chan-1", _PAYLOAD)
        store.assert_called_once()
        assert store.call_args[0][0] == "logs:chan-1"


class TestEnvelopeParity:
    """Both transports must carry the same kwargs, or the consumer behaves differently
    depending on how the log arrived."""

    def test_kwargs_match_across_transports(self, monkeypatch, kombu, redis_client):
        monkeypatch.delenv("LOG_TRANSPORT", raising=False)
        LogPublisher.publish("chan-1", _PAYLOAD)
        celery_kwargs = kombu.publish.call_args.kwargs["body"]["kwargs"]

        monkeypatch.setenv("LOG_TRANSPORT", "redis")
        LogPublisher.publish("chan-1", _PAYLOAD)
        redis_kwargs = json.loads(redis_client.rpush.call_args[0][1])["kwargs"]

        assert celery_kwargs == redis_kwargs
