"""Redis Client with Sentinel HA Support

Dual-mode Redis configuration:
- Standalone mode: traditional redis.Redis() when REDIS_SENTINEL_MODE is absent/False
- Sentinel mode: Sentinel.master_for() when REDIS_SENTINEL_MODE=True

Mode is detected from {prefix}SENTINEL_MODE env var (LLMW pattern).
In Sentinel mode, REDIS_HOST/REDIS_PORT point to the K8s Sentinel service endpoint.
Master name defaults to "mymaster" (configurable via REDIS_SENTINEL_MASTER_NAME env var).
REDIS_PASSWORD is reused for Sentinel auth.

Retry: 10 attempts, 5s initial, 1.5x backoff, ±20% jitter.
"""

import logging
import os
import random
import time
from typing import Any

import redis
from redis.sentinel import Sentinel

from unstract.core.cache.exceptions import RedisSentinelConnectionError

logger = logging.getLogger(__name__)

_SENTINEL_MAX_RETRIES = 10
_SENTINEL_INITIAL_DELAY = 5  # seconds
_SENTINEL_BACKOFF_MULTIPLIER = 1.5
_SENTINEL_JITTER_MIN = 0.8
_SENTINEL_JITTER_MAX = 1.2
_SENTINEL_MASTER_NAME = os.getenv("REDIS_SENTINEL_MASTER_NAME", "mymaster")


def _is_sentinel_mode(env_prefix: str) -> bool:
    return os.getenv(f"{env_prefix}SENTINEL_MODE", "False").strip().lower() == "true"


def create_redis_client(
    env_prefix: str = "REDIS_",
    decode_responses: bool = True,
    socket_connect_timeout: int = 5,
    socket_timeout: int = 5,
    max_connections: int | None = None,
    db: int | None = None,
) -> redis.Redis:
    """Factory to create a Redis client in Standalone or Sentinel mode.

    Mode is detected from {env_prefix}SENTINEL_MODE env var.
    In Sentinel mode, {env_prefix}HOST and {env_prefix}PORT point to the
    Sentinel service endpoint (K8s DNS). Master name from REDIS_SENTINEL_MASTER_NAME env.

    Args:
        env_prefix: Env var prefix (e.g. "REDIS_" or "CACHE_REDIS_").
        decode_responses: Whether to decode responses to strings.
        socket_connect_timeout: Connection timeout in seconds.
        socket_timeout: Socket timeout in seconds.
        max_connections: Optional max connections for standalone ConnectionPool.
        db: Optional DB index override.

    Returns:
        Configured redis.Redis client (standalone or Sentinel-backed).

    Raises:
        RedisSentinelConnectionError: After exhausting retries in Sentinel mode.
    """
    if _is_sentinel_mode(env_prefix):
        return _create_sentinel_client(
            env_prefix=env_prefix,
            decode_responses=decode_responses,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
            db_override=db,
        )
    else:
        return _create_standalone_client(
            env_prefix=env_prefix,
            decode_responses=decode_responses,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
            max_connections=max_connections,
            db_override=db,
        )


def _create_standalone_client(
    env_prefix: str,
    decode_responses: bool,
    socket_connect_timeout: int,
    socket_timeout: int,
    max_connections: int | None,
    db_override: int | None = None,
) -> redis.Redis:
    host = os.getenv(f"{env_prefix}HOST", os.getenv("REDIS_HOST", "localhost"))
    port = int(os.getenv(f"{env_prefix}PORT", os.getenv("REDIS_PORT", "6379")))
    password = os.getenv(f"{env_prefix}PASSWORD", os.getenv("REDIS_PASSWORD"))
    username = os.getenv(
        f"{env_prefix}USER",
        os.getenv(f"{env_prefix}USERNAME", os.getenv("REDIS_USER")),
    )
    db = (
        db_override
        if db_override is not None
        else int(os.getenv(f"{env_prefix}DB", os.getenv("REDIS_DB", "0")))
    )

    logger.info("Redis standalone mode enabled. Connecting to %s:%s", host, port)

    kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "password": password,
        "username": username,
        "db": db,
        "decode_responses": decode_responses,
        "socket_connect_timeout": socket_connect_timeout,
        "socket_timeout": socket_timeout,
    }

    if max_connections is not None:
        pool = redis.ConnectionPool(max_connections=max_connections, **kwargs)
        return redis.Redis(connection_pool=pool)

    return redis.Redis(**kwargs)


def _create_sentinel_client(
    env_prefix: str,
    decode_responses: bool,
    socket_connect_timeout: int,
    socket_timeout: int,
    db_override: int | None = None,
) -> redis.Redis:
    # Reuse HOST/PORT — in Sentinel mode these point to the Sentinel service
    host = os.getenv(f"{env_prefix}HOST", os.getenv("REDIS_HOST", "localhost"))
    port = int(os.getenv(f"{env_prefix}PORT", os.getenv("REDIS_PORT", "26379")))
    password = os.getenv(f"{env_prefix}PASSWORD", os.getenv("REDIS_PASSWORD"))
    username = os.getenv(
        f"{env_prefix}USER",
        os.getenv(f"{env_prefix}USERNAME", os.getenv("REDIS_USER")),
    )
    db = (
        db_override
        if db_override is not None
        else int(os.getenv(f"{env_prefix}DB", os.getenv("REDIS_DB", "0")))
    )

    logger.info(
        "Redis Sentinel mode enabled. Connecting to sentinel at %s:%s, master: %s",
        host,
        port,
        _SENTINEL_MASTER_NAME,
    )

    # Sentinel auth reuses the same password
    sentinel_kwargs: dict[str, Any] = {}
    if password:
        sentinel_kwargs["password"] = password
    if username:
        sentinel_kwargs["username"] = username

    last_error: Exception | None = None
    for attempt in range(_SENTINEL_MAX_RETRIES):
        try:
            sentinel = Sentinel(
                [(host, port)],
                socket_connect_timeout=socket_connect_timeout,
                socket_timeout=socket_timeout,
                sentinel_kwargs=sentinel_kwargs,
            )
            master_kwargs: dict[str, Any] = {
                "socket_connect_timeout": socket_connect_timeout,
                "socket_timeout": socket_timeout,
                "decode_responses": decode_responses,
                "db": db,
            }
            if password:
                master_kwargs["password"] = password
            if username:
                master_kwargs["username"] = username

            client = sentinel.master_for(_SENTINEL_MASTER_NAME, **master_kwargs)
            client.ping()
            return client
        except (
            redis.exceptions.ConnectionError,
            redis.exceptions.TimeoutError,
            OSError,
        ) as e:
            last_error = e
            if attempt >= _SENTINEL_MAX_RETRIES - 1:
                break
            delay = (
                _SENTINEL_INITIAL_DELAY
                * (_SENTINEL_BACKOFF_MULTIPLIER**attempt)
                * random.uniform(_SENTINEL_JITTER_MIN, _SENTINEL_JITTER_MAX)
            )
            logger.warning(
                "Sentinel connection attempt %d/%d failed. Retrying in %.1fs. Error: %s",
                attempt + 1,
                _SENTINEL_MAX_RETRIES,
                delay,
                e,
            )
            time.sleep(delay)
        except Exception as e:
            # Non-retriable errors (auth, config) — fail fast
            raise RedisSentinelConnectionError(
                f"Non-retriable error connecting to Redis Sentinel: {e}"
            ) from e

    raise RedisSentinelConnectionError(
        f"Failed to connect to Redis Sentinel after {_SENTINEL_MAX_RETRIES} retries "
        f"(~5 minutes).\n"
        f"Sentinel endpoint: {host}:{port}\n"
        f"Service: {_SENTINEL_MASTER_NAME}\n"
        f"Check Sentinel availability, REDIS_HOST, REDIS_PORT, and "
        f"REDIS_SENTINEL_MODE configuration.\n"
        f"Last error: {last_error}"
    )


class RedisClient:
    """Base Redis client with comprehensive operations."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        username: str | None = None,
        password: str | None = None,
        db: int = 0,
        decode_responses: bool = True,
        socket_connect_timeout: int = 5,
        socket_timeout: int = 5,
    ):
        self.redis_client = redis.Redis(
            host=host,
            port=port,
            username=username,
            password=password,
            db=db,
            decode_responses=decode_responses,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
        )

    # Basic key-value operations
    def get(self, key: str) -> Any:
        return self.redis_client.get(key)

    def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        return self.redis_client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)

    def setex(self, key: str, time: int, value: Any) -> bool:
        return self.redis_client.setex(key, time, value)

    def delete(self, *keys: str) -> int:
        return self.redis_client.delete(*keys)

    def exists(self, *keys: str) -> int:
        return self.redis_client.exists(*keys)

    # TTL operations
    def expire(self, key: str, time: int) -> bool:
        return self.redis_client.expire(key, time)

    def ttl(self, key: str) -> int:
        return self.redis_client.ttl(key)

    def persist(self, key: str) -> bool:
        return self.redis_client.persist(key)

    # Batch operations
    def mget(self, keys: list[str]) -> list[Any]:
        return self.redis_client.mget(keys)

    def mset(self, mapping: dict[str, Any]) -> bool:
        return self.redis_client.mset(mapping)

    # Key scanning and patterns
    def keys(self, pattern: str = "*") -> list[str]:
        return self.redis_client.keys(pattern)

    def scan(
        self, cursor: int = 0, match: str | None = None, count: int | None = None
    ) -> tuple[int, list[str]]:
        return self.redis_client.scan(cursor=cursor, match=match, count=count)

    def incr(self, key: str) -> int:
        return self.redis_client.incr(key)

    # Pipeline support
    def pipeline(self, transaction: bool = True) -> redis.client.Pipeline:
        return self.redis_client.pipeline(transaction=transaction)

    # Health check
    def ping(self) -> bool:
        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False

    # Connection info
    def info(self, section: str | None = None) -> dict[str, Any]:
        return self.redis_client.info(section=section)

    @classmethod
    def from_env(cls, env_prefix: str = "REDIS_") -> "RedisClient":
        """Create client from environment variables, with Sentinel support.

        When {env_prefix}SENTINEL_MODE is True, returns a RedisClient backed
        by a Sentinel-managed connection. Otherwise uses standalone mode.
        """
        if _is_sentinel_mode(env_prefix):
            instance = cls.__new__(cls)
            instance.redis_client = create_redis_client(
                env_prefix=env_prefix, decode_responses=True
            )
            return instance
        else:
            host = os.getenv(f"{env_prefix}HOST", os.getenv("REDIS_HOST", "localhost"))
            port = int(os.getenv(f"{env_prefix}PORT", os.getenv("REDIS_PORT", "6379")))
            username = os.getenv(
                f"{env_prefix}USER",
                os.getenv(f"{env_prefix}USERNAME", os.getenv("REDIS_USER")),
            )
            password = os.getenv(f"{env_prefix}PASSWORD", os.getenv("REDIS_PASSWORD"))
            db = int(os.getenv(f"{env_prefix}DB", os.getenv("REDIS_DB", "0")))

            return cls(
                host=host,
                port=port,
                username=username,
                password=password,
                db=db,
            )
