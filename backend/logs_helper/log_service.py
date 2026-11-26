from utils.cache_service import CacheService
from utils.log_channel import log_channel_id


class LogService:
    @staticmethod
    def remove_logs_on_logout(session_id: str) -> None:
        if session_id:
            key_pattern = f"{LogService.generate_redis_key(session_id=session_id)}*"

            # Delete keys matching the pattern
            CacheService.clear_cache(key_pattern=key_pattern)

    @staticmethod
    def generate_redis_key(session_id):
        """Generate a Redis key for logs based on the provided session_id.

        Parameters:
        session_id (str): The session identifier to include in the Redis key.

        The key carries the session's log channel id, never the session key.

        Returns:
        str: The constructed Redis key.
        """
        return f"logs:{log_channel_id(session_id)}"
