from typing import Any, Optional, Union

from account.custom_cache import CustomCache
from account.dto import UserSessionInfo
from django.conf import settings
from django.core.cache import cache


class CacheService:
    @staticmethod
    def get_key(key: str) -> Optional[Any]:
        data = cache.get(str(key))
        if data is not None:
            return data.decode("utf-8")
        return data

    @staticmethod
    def set_key(key: str, value: Any) -> None:
        cache.set(
            str(key),
            value,
            int(settings.CACHE_TTL_SEC),
        )

    @staticmethod
    def clear_cache(key_pattern: str) -> Any:
        """Delete keys in bulk based on the key pattern."""
        cache.delete_pattern(key_pattern)

    @staticmethod
    def set_cookie(cookie: str, token: dict[str, Any]) -> None:
        cache.set(cookie, token)

    @staticmethod
    def get_cookie(cookie: str) -> dict[str, Any]:
        data: dict[str, Any] = cache.get(cookie)
        return data

    @staticmethod
    def set_user_session_info(
        user_session_info: Union[UserSessionInfo, dict[str, Any]]
    ) -> None:
        if isinstance(user_session_info, UserSessionInfo):
            email = user_session_info.email
            user_session = user_session_info.to_dict()
        else:
            email = user_session_info["email"]
            user_session = user_session_info
        session_info_key: str = CacheService.get_user_session_info_key(email)
        cache.set(
            session_info_key,
            user_session,
            int(settings.SESSION_EXPIRATION_TIME_IN_SECOND),
        )

    @staticmethod
    def get_user_session_info(email: str) -> dict[str, Any]:
        session_info_key: str = CacheService.get_user_session_info_key(email)
        data: dict[str, Any] = cache.get(session_info_key)
        return data

    @staticmethod
    def get_user_session_info_key(email: str) -> str:
        session_info_key: str = f"session:{email}"
        return session_info_key

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
    def add_cookie_id_to_user(user_id: str, cookie_id: str) -> None:
        custom_cache = CustomCache()
        key: str = f"{user_id}|cookies"
        custom_cache.rpush(key, cookie_id)

    @staticmethod
    def remove_cookie_id_from_user(user_id: str, cookie_id: str) -> None:
        custom_cache = CustomCache()
        key: str = f"{user_id}|cookies"
        custom_cache.lrem(key, cookie_id)

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
