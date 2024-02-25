from django_redis import get_redis_connection


class CustomCache:
    def __init__(self) -> None:
        self.cache = get_redis_connection("default")

    def rpush(self, key: str, value: str) -> None:
        self.cache.rpush(key, value)

    def lrem(self, key: str, value: str) -> None:
        self.cache.lrem(key, value)
