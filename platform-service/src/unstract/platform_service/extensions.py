from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import redis
from peewee import PostgresqlDatabase

db = PostgresqlDatabase(None)

# Redis connection pool (initialized lazily)
_redis_pool: redis.ConnectionPool | None = None


def get_redis_pool() -> redis.ConnectionPool:
    """Get or create the Redis connection pool.

    Returns:
        redis.ConnectionPool: Shared connection pool for Redis operations.
    """
    global _redis_pool
    if _redis_pool is None:
        # Import here to avoid circular imports
        from unstract.platform_service.env import Env

        _redis_pool = redis.ConnectionPool(
            host=Env.REDIS_HOST,
            port=Env.REDIS_PORT,
            username=Env.REDIS_USERNAME,
            password=Env.REDIS_PASSWORD,
            max_connections=10,
            decode_responses=False,
        )
    return _redis_pool


def get_redis_client() -> redis.Redis:
    """Get a Redis client using the shared connection pool.

    Returns:
        redis.Redis: Redis client instance.
    """
    return redis.Redis(connection_pool=get_redis_pool())


@contextmanager
def safe_cursor(query: str, params: tuple = ()) -> Generator[Any, None, None]:
    """Execute a query and ensure cursor is always closed.

    Args:
        query: SQL query to execute.
        params: Query parameters.

    Yields:
        Database cursor.
    """
    cursor = db.execute_sql(query, params)
    try:
        yield cursor
    finally:
        cursor.close()
