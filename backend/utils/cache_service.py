import json
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django_redis import get_redis_connection

redis_cache = get_redis_connection("default")


class CacheService:
    @staticmethod
    def get_key(key: str) -> Any | None:
        data = cache.get(str(key))
        if data is not None:
            if isinstance(data, bytes):
                return data.decode("utf-8")
            else:
                return data
        return data

    @staticmethod
    def set_key(key: str, value: Any, expire: int = int(settings.CACHE_TTL_SEC)) -> None:
        cache.set(
            str(key),
            value,
            expire,
        )

    @staticmethod
    def get_all_keys(key_pattern: str) -> Any:
        keys = redis_cache.keys(key_pattern)
        # Ensure all keys are strings
        return [key.decode("utf-8") if isinstance(key, bytes) else key for key in keys]

    @staticmethod
    def clear_cache(key_pattern: str) -> Any:
        """Delete keys in bulk based on the key pattern."""
        cache.delete_pattern(key_pattern)

    @staticmethod
    def check_a_key_exist(key: str, version: Any = None) -> bool:
        data: bool = cache.has_key(key, version)
        return data

    @staticmethod
    def delete_a_key(key: str, version: Any = None) -> None:
        cache.delete(key, version)

    @staticmethod
    def set_user_organizations(user_id: str, organizations: list[str]) -> None:
        key: str = f"{user_id}|organizations"
        cache.set(key, list(organizations))

    @staticmethod
    def get_user_organizations(user_id: str) -> Any:
        key: str = f"{user_id}|organizations"
        return cache.get(key)

    @staticmethod
    def remove_user_organizations(user_id: str) -> Any:
        key: str = f"{user_id}|organizations"
        return cache.delete(key)

    @staticmethod
    def rpush(key: str, value: str) -> None:
        redis_cache.rpush(key, value)

    @staticmethod
    def lpop(key: str) -> Any:
        return redis_cache.lpop(key)

    @staticmethod
    def lrem(key: str, value: str) -> None:
        redis_cache.lrem(key, value)

    @staticmethod
    def lrange(key, start_index, end_index) -> list[Any]:
        return redis_cache.lrange(key, start_index, end_index)

    @staticmethod
    def hset(
        key: str,
        field: str = None,
        value: Any = None,
        mapping: dict[str, Any] = None,
        expire_time: int = int(settings.CACHE_TTL_SEC),
    ) -> None:
        """Set Redis hash fields. Supports both single field-value and full mapping.

        Args:
            key (str): The key of the Redis hash.
            field (str, optional): The field to set. Defaults to None.
            value (Any, optional): The value to set. Defaults to None.
            mapping (dict[str, Any], optional): The mapping of fields to values.
                Defaults to None.
            expire_time (int, optional): The expiration time for hash in seconds.
                Defaults to int(settings.CACHE_TTL_SEC).
        """
        if mapping is not None:
            redis_cache.hset(key, mapping=mapping)
        elif field is not None and value is not None:
            redis_cache.hset(key, field, value)
        else:
            raise ValueError("Provide either 'mapping' or both 'field' and 'value'")

        redis_cache.expire(key, expire_time)

    @staticmethod
    def hget(key: str, field: str) -> Any:
        """Get a value from a Redis hash."""
        return redis_cache.hget(key, field)

    @staticmethod
    def hgetall(key: str) -> Any:
        """Get all values from a Redis hash."""
        return redis_cache.hgetall(key)

    @staticmethod
    def hincrby(key: str, field: str, increment: int) -> None:
        """Increment a value in a Redis hash."""
        redis_cache.hincrby(key, field, increment)

    @staticmethod
    def exists(key: str) -> bool:
        """Check if a key exists in Redis."""
        return redis_cache.exists(key)

    @staticmethod
    def rpush_with_expire(
        key: str, value: Any, expire: int = int(settings.CACHE_TTL_SEC)
    ) -> None:
        """Push a value to a Redis list and reset the list's TTL in a single atomic operation.

        Args:
            key (str): The key of the Redis list.
            value (Any): The value to push to the list.
            expire (int, optional): The expiration time for list in seconds.
                Defaults to int(settings.CACHE_TTL_SEC).

        Returns:
            None
        """
        pipe = redis_cache.pipeline()
        pipe.rpush(key, json.dumps(value))
        pipe.expire(key, expire)
        pipe.execute()

    @staticmethod
    def lrange_json(key: str, start_index: int = 0, end_index: int = -1) -> list[Any]:
        """Get all items from list and parse JSON.

        Args:
            key (str): The key of the Redis list.
            start_index (int, optional): The starting index for the range.
                Defaults to 0.
            end_index (int, optional): The ending index for the range.
                Defaults to -1.

        Returns:
            list[Any]: A list of parsed JSON values from the list.
        """
        results = redis_cache.lrange(key, start_index, end_index)
        if not results:
            return []
        return [
            json.loads(r.decode("utf-8") if isinstance(r, bytes) else r) for r in results
        ]

    @staticmethod
    def remove_all_session_keys(
        user_id: str | None = None,
        cookie_id: str | None = None,
        key: str | None = None,
    ) -> None:
        if cookie_id is not None:
            cache.delete(cookie_id)
        if user_id is not None:
            cache.delete(user_id)
            CacheService.remove_user_organizations(user_id)
        if key is not None:
            cache.delete(key)

    # @staticmethod
    # def get_cookie_ids_for_user(user_id: str) -> list[str]:
    #     custom_cache = CustomCache()
    #     key: str = f"{user_id}|cookies"
    #     cookie_ids = custom_cache.lrange(key, 0, -1)
    #     return cookie_ids


# KEY_FUNCTION for cache settings
def custom_key_function(key: str, key_prefix: str, version: int) -> str:
    version = int(version)
    if version > 1:
        return f"{key_prefix}:{version}:{key}"
    if key_prefix:
        return f"{key_prefix}:{key}"
    else:
        return key
