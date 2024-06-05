from django_redis import get_redis_connection

class LogService:
    @staticmethod
    def remove_logs_on_logout(session_id):
        
        if session_id:
            # Get the Redis connection
            r = get_redis_connection("default")

            # Construct the Redis key pattern to match keys associated with the session ID
            redis_key_pattern = f"logs:{session_id}*"

            # Retrieve keys matching the pattern and delete them
            keys = r.keys(redis_key_pattern)
            if keys:
                r.delete(*keys)
