from utils.cache_service import CacheService


class LogService:
    @staticmethod
    def remove_logs_on_logout(session_id: str) -> None:

        if session_id:
            key_pattern = f"logs:{session_id}*"

            # Delete keys matching the pattern
            CacheService.clear_cache(key_pattern=key_pattern)
