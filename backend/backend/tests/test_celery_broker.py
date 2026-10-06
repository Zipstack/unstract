"""When the backend requires the Celery broker settings, and the URL it builds.

The broker is needed only by the Celery log transport, so a Redis-only deployment
must start without it, while the Celery transport keeps failing fast on a missing
setting. With the settings present the URL must be exactly what it always was.
"""

from __future__ import annotations

import httpx
import pytest

from backend.celery_broker import (
    CELERY_BROKER_BASE_URL,
    CELERY_BROKER_PASS,
    CELERY_BROKER_USER,
    build_broker_url,
    required_broker_settings,
)

_ALL = (CELERY_BROKER_BASE_URL, CELERY_BROKER_USER, CELERY_BROKER_PASS)
_FULL = {
    CELERY_BROKER_BASE_URL: "amqp://unstract-rabbitmq:5672//",
    CELERY_BROKER_USER: "admin",
    CELERY_BROKER_PASS: "password",
}


def _missing(env: dict[str, str]) -> list[str]:
    """What ``get_required_setting`` would add to ``missing_settings``."""
    return [key for key in required_broker_settings(env) if not env.get(key)]


class TestRequiredSettings:
    def test_redis_transport_without_a_broker_requires_nothing(self):
        env = {"LOG_TRANSPORT": "redis"}
        assert required_broker_settings(env) == ()
        assert build_broker_url(None, None, None) == ""

    @pytest.mark.parametrize("transport", [None, "celery", "", "rabbit"])
    def test_celery_transport_without_a_broker_reports_all_three(self, transport):
        env = {} if transport is None else {"LOG_TRANSPORT": transport}
        assert _missing(env) == list(_ALL)

    @pytest.mark.parametrize("transport", ["redis", " Redis ", "celery"])
    def test_a_full_broker_config_reports_nothing(self, transport):
        assert _missing({**_FULL, "LOG_TRANSPORT": transport}) == []

    @pytest.mark.parametrize("transport", ["redis", "celery"])
    @pytest.mark.parametrize("dropped", [CELERY_BROKER_USER, CELERY_BROKER_PASS])
    def test_a_base_url_without_credentials_is_reported(self, transport, dropped):
        env = {**_FULL, "LOG_TRANSPORT": transport}
        del env[dropped]
        assert _missing(env) == [dropped]


class TestBrokerUrl:
    @pytest.mark.parametrize(
        ("base_url", "user", "password"),
        [
            ("amqp://unstract-rabbitmq:5672//", "admin", "password"),
            ("amqp://rabbit.svc:5672/vhost", "us@er", "p@ss:w/rd#%?"),
            ("redis://localhost:6379", "guest", "guest"),
        ],
    )
    def test_matches_the_previous_construction(self, base_url, user, password):
        expected = str(
            httpx.URL(base_url).copy_with(username=user, password=password)
        )
        assert build_broker_url(base_url, user, password) == expected

    def test_special_characters_are_escaped(self):
        assert (
            build_broker_url("amqp://rabbit.svc:5672/vhost", "us@er", "p@ss:w/rd#%?")
            == "amqp://us%40er:p%40ss%3Aw%2Frd%23%%3F@rabbit.svc:5672/vhost"
        )

    @pytest.mark.parametrize("base_url", [None, ""])
    def test_no_base_url_yields_an_empty_url(self, base_url):
        assert build_broker_url(base_url, "u", "p") == ""
