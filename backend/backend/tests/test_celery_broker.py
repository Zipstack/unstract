"""When the backend requires the Celery broker settings, and the URL it builds.

The broker is needed only by the Celery log transport, so a Redis-only deployment
must start without it, while the Celery transport keeps failing fast on a missing
setting. With the settings present the URL must be exactly what it always was.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

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

    @pytest.mark.parametrize("transport", [None, "celery"])
    @pytest.mark.parametrize("dropped", [CELERY_BROKER_USER, CELERY_BROKER_PASS])
    def test_celery_transport_reports_a_missing_credential(self, transport, dropped):
        env = dict(_FULL) if transport is None else {**_FULL, "LOG_TRANSPORT": transport}
        del env[dropped]
        assert _missing(env) == [dropped]

    def test_redis_transport_with_a_bare_base_url_requires_nothing(self):
        env = {CELERY_BROKER_BASE_URL: _FULL[CELERY_BROKER_BASE_URL]}
        env["LOG_TRANSPORT"] = "redis"
        assert required_broker_settings(env) == ()


class TestBrokerUrl:
    @pytest.mark.parametrize(
        ("base_url", "user", "password", "expected"),
        [
            (
                "amqp://unstract-rabbitmq:5672//",
                "admin",
                "password",
                "amqp://admin:password@unstract-rabbitmq:5672//",
            ),
            (
                "amqp://rabbit.svc:5672/vhost",
                "us@er",
                "p@ss:w/rd#%?",
                "amqp://us%40er:p%40ss%3Aw%2Frd%23%%3F@rabbit.svc:5672/vhost",
            ),
            (
                "redis://localhost:6379",
                "guest",
                "guest",
                "redis://guest:guest@localhost:6379",
            ),
        ],
    )
    def test_builds_the_credentialed_url(self, base_url, user, password, expected):
        assert build_broker_url(base_url, user, password) == expected

    @pytest.mark.parametrize("base_url", [None, ""])
    def test_no_base_url_yields_an_empty_url(self, base_url):
        assert build_broker_url(base_url, "u", "p") == ""


_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[2]
_MISSING_MARKER = "Below required settings are missing."


def _import_settings(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    """Import the real ``settings/base.py`` in a fresh interpreter.

    It runs once per process and raises at its end when anything is missing, so a
    subprocess is the only way to see what it enforces under a given environment.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in (*_ALL, "LOG_TRANSPORT")
    }
    env.update(env_overrides)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import backend.settings.base as b; print(repr(b.CELERY_BROKER_URL))",
        ],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _reported_missing(result: subprocess.CompletedProcess) -> str:
    assert result.returncode != 0, result.stdout
    assert _MISSING_MARKER in result.stderr, result.stderr
    return result.stderr.split(_MISSING_MARKER, 1)[1]


class TestSettingsWiring:
    """Exercise the shipping settings module, not just the helper it calls."""

    @pytest.mark.parametrize("transport", [None, "celery"])
    def test_celery_transport_without_a_broker_fails_at_import(self, transport):
        overrides = {} if transport is None else {"LOG_TRANSPORT": transport}
        missing = _reported_missing(_import_settings(overrides))
        for key in _ALL:
            assert key in missing

    def test_redis_transport_without_a_broker_imports(self):
        result = _import_settings({"LOG_TRANSPORT": "redis"})
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().splitlines()[-1] == "''"

    def test_redis_transport_with_a_bare_base_url_imports(self):
        # The base URL may outlive its credentials in a deployment's config; on
        # Redis the resulting credential-less URL is built but never dialled.
        result = _import_settings(
            {"LOG_TRANSPORT": "redis", CELERY_BROKER_BASE_URL: "amqp://h:5672//"}
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().splitlines()[-1] == "'amqp://h:5672//'"

    def test_celery_transport_with_a_bare_base_url_fails_at_import(self):
        missing = _reported_missing(
            _import_settings({CELERY_BROKER_BASE_URL: "amqp://h:5672//"})
        )
        assert CELERY_BROKER_USER in missing
        assert CELERY_BROKER_PASS in missing
        assert CELERY_BROKER_BASE_URL not in missing

    def test_a_full_broker_config_builds_the_same_url(self):
        result = _import_settings(
            {
                CELERY_BROKER_BASE_URL: "amqp://rabbit.svc:5672/vhost",
                CELERY_BROKER_USER: "us@er",
                CELERY_BROKER_PASS: "p@ss:w/rd#%?",
            }
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().splitlines()[-1] == (
            "'amqp://us%40er:p%40ss%3Aw%2Frd%23%%3F@rabbit.svc:5672/vhost'"
        )
