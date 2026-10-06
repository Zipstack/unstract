"""Celery broker settings, resolved from the environment.

Kept free of Django and of ``unstract.core.pubsub_helper`` (which opens a kombu
connection object at import) so ``settings/base.py`` can import it cheaply and the
rules can be tested on their own.
"""

from collections.abc import Mapping

import httpx

CELERY_BROKER_BASE_URL = "CELERY_BROKER_BASE_URL"
CELERY_BROKER_USER = "CELERY_BROKER_USER"
CELERY_BROKER_PASS = "CELERY_BROKER_PASS"
_BROKER_SETTINGS = (CELERY_BROKER_BASE_URL, CELERY_BROKER_USER, CELERY_BROKER_PASS)


def uses_redis_log_transport(env: Mapping[str, str]) -> bool:
    """Mirror ``unstract.core.pubsub_helper.use_redis_log_transport``."""
    return env.get("LOG_TRANSPORT", "celery").strip().lower() == "redis"


def required_broker_settings(env: Mapping[str, str]) -> tuple[str, ...]:
    """Broker settings that must be present in ``env``.

    The Celery log transport publishes over the broker, so it needs all three. On
    the Redis transport the broker is optional, but a base URL that is set still
    needs its credentials rather than yielding a credential-less URL.
    """
    if uses_redis_log_transport(env) and not env.get(CELERY_BROKER_BASE_URL):
        return ()
    return _BROKER_SETTINGS


def build_broker_url(base_url: str | None, user: str | None, password: str | None) -> str:
    """Return the broker URL with credentials, or "" when no base URL is set."""
    if not base_url:
        return ""
    return str(httpx.URL(base_url).copy_with(username=user, password=password))
