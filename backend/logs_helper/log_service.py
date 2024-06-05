from django_redis import get_redis_connection


class LogService:
    @staticmethod
    def remove_logs_on_logout(session_id):

        if session_id:
            # Get the Redis connection
            r = get_redis_connection("default")

            key_pattern = f"logs:{session_id}*"

            # Retrieve keys matching the pattern and delete them
            keys = r.keys(key_pattern)
            if keys:
                r.delete(*keys)
