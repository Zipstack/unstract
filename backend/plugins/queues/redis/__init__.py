from .redis_queue import RedisQueue

metadata = {
    "name": RedisQueue.__name__,
    "version": "1.0.0",
    "connector": RedisQueue,
    "description": "Redis Queue connector",
    "is_active": True,
}
