from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import redis
from peewee import PostgresqlDatabase

from unstract.core.cache.redis_client import create_redis_client

db = PostgresqlDatabase(None)

# Lazy singleton — avoids import-time Redis connection that blocks startup
_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    """Get a Redis client, with Sentinel support and connection pooling.

    In standalone mode, uses a ConnectionPool with max_connections=10.
    In Sentinel mode, master_for() manages its own pooling.

    Returns:
        redis.Redis: Redis client instance.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = create_redis_client(
            decode_responses=False,
            max_connections=10,
        )
    return _redis_client


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
