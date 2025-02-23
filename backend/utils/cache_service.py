from typing import Any, Optional

from django.conf import settings
from django.core.cache import cache
from django_redis import get_redis_connection

redis_cache = get_redis_connection("default")


class CacheService:
    @staticmethod
    def get_key(key: str) -> Optional[Any]:
        data = cache.get(str(key))
        if data is not None:
            if isinstance(data, bytes):
                return data.decode("utf-8")
            else:
                return data
        return data

    @staticmethod
    def set_key(
        key: str, value: Any, expire: int = int(settings.CACHE_TTL_SEC)
    ) -> None:
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
    def remove_all_session_keys(
        user_id: Optional[str] = None,
        cookie_id: Optional[str] = None,
        key: Optional[str] = None,
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
