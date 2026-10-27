"""clear_cache_optimized falls back to delete_pattern on a Redis outage.

redis-py's ConnectionError/TimeoutError derive from RedisError, not from the
builtins of the same name, so catching only the builtins skipped the fallback.
"""

from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from utils import cache_service
from utils.cache_service import CacheService


@pytest.mark.parametrize("error", [RedisConnectionError("down"), RedisTimeoutError("slow")])
def test_redis_error_falls_back_to_delete_pattern(error: Exception) -> None:
    connection = MagicMock()
    connection.scan.side_effect = error

    with (
        patch.object(cache_service, "redis_cache", connection),
        patch.object(cache_service, "cache") as cache,
    ):
        CacheService.clear_cache_optimized("file_active:*")

    cache.delete_pattern.assert_called_once_with("file_active:*")


def test_fallback_failure_reraises_original_error() -> None:
    connection = MagicMock()
    original = RedisConnectionError("down")
    connection.scan.side_effect = original

    with (
        patch.object(cache_service, "redis_cache", connection),
        patch.object(cache_service, "cache") as cache,
    ):
        cache.delete_pattern.side_effect = RedisConnectionError("still down")
        with pytest.raises(RedisConnectionError) as exc_info:
            CacheService.clear_cache_optimized("file_active:*")

    cache.delete_pattern.assert_called_once_with("file_active:*")
    assert exc_info.value is original


def test_redis_error_on_a_specific_db_is_not_masked_by_the_fallback() -> None:
    """The fallback clears the default cache's DB, never the one asked for."""
    connection = MagicMock()
    original = RedisTimeoutError("slow")
    connection.scan.side_effect = original

    with (
        patch.object(cache_service, "create_redis_client", return_value=connection),
        patch.object(cache_service, "cache") as cache,
    ):
        with pytest.raises(RedisTimeoutError) as exc_info:
            CacheService.clear_cache_optimized("file_active:*", db=1)

    cache.delete_pattern.assert_not_called()
    assert exc_info.value is original
