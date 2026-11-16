"""Shared test helper: forget everything API key usage keeps in Redis."""

from django.conf import settings
from django_redis import get_redis_connection


def clear_usage_redis() -> None:
    """Delete every key under this test worker's usage prefix.

    Pending hashes, batches, the flush trigger and lock, failure counts and
    set-aside batches alike, so no test sees another's leftovers.
    """
    redis = get_redis_connection("default")
    keys = list(redis.scan_iter(f"{settings.API_KEY_USAGE_REDIS_PREFIX}:*"))
    if keys:
        redis.delete(*keys)
