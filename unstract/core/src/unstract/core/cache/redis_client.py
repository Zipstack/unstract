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
_DEFAULT_SENTINEL_MASTER_NAME = os.getenv("REDIS_SENTINEL_MASTER_NAME", "mymaster")


def _is_sentinel_mode(env_prefix: str) -> bool:
    return os.getenv(f"{env_prefix}SENTINEL_MODE", "False").strip().lower() == "true"


def create_redis_client(
    env_prefix: str = "REDIS_",
    decode_responses: bool = True,
    socket_connect_timeout: int = 5,
    socket_timeout: int = 5,
    max_connections: int | None = None,
    health_check_interval: int = 0,
    db: int | None = None,
) -> redis.Redis:
    """Factory to create a Redis client in Standalone or Sentinel mode.

    Mode is detected from {env_prefix}SENTINEL_MODE env var.
    In Sentinel mode, {env_prefix}HOST and {env_prefix}PORT point to the
    Sentinel service endpoint (K8s DNS). Master name from
    {env_prefix}SENTINEL_MASTER_NAME env (falls back to REDIS_SENTINEL_MASTER_NAME).

    Args:
        env_prefix: Env var prefix (e.g. "REDIS_" or "CACHE_REDIS_").
        decode_responses: Whether to decode responses to strings.
        socket_connect_timeout: Connection timeout in seconds.
        socket_timeout: Socket timeout in seconds.
        max_connections: Optional max connections for ConnectionPool.
        health_check_interval: Proactive health check interval in seconds (0=disabled).
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
            health_check_interval=health_check_interval,
            max_connections=max_connections,
            db_override=db,
        )
    else:
        return _create_standalone_client(
            env_prefix=env_prefix,
            decode_responses=decode_responses,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
            max_connections=max_connections,
            health_check_interval=health_check_interval,
            db_override=db,
        )


def _resolve_redis_env(
    env_prefix: str, default_port: str = "6379", db_override: int | None = None
) -> dict[str, Any]:
    """Read common Redis env vars into a dict."""
    host = os.getenv(f"{env_prefix}HOST", os.getenv("REDIS_HOST", "localhost"))
    port = int(os.getenv(f"{env_prefix}PORT", os.getenv("REDIS_PORT", default_port)))
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
    ssl = os.getenv(f"{env_prefix}SSL", "false").strip().lower() == "true"
    result: dict[str, Any] = {
        "host": host,
        "port": port,
        "password": password,
        "username": username,
        "db": db,
        "ssl": ssl,
    }
    if ssl:
        result["ssl_cert_reqs"] = os.getenv(f"{env_prefix}SSL_CERT_REQS", "required")
    return result


def _build_connection_kwargs(
    env: dict[str, Any],
    decode_responses: bool,
    socket_connect_timeout: int,
    socket_timeout: int,
    health_check_interval: int = 0,
    max_connections: int | None = None,
    include_auth_only: bool = False,
) -> dict[str, Any]:
    """Build kwargs dict for Redis/Sentinel connections.

    Args:
        include_auth_only: If True, only include password/username (for sentinel_kwargs).
    """
    if include_auth_only:
        kwargs: dict[str, Any] = {
            "socket_connect_timeout": socket_connect_timeout,
            "socket_timeout": socket_timeout,
        }
        if env.get("password"):
            kwargs["password"] = env["password"]
        if env.get("username"):
            kwargs["username"] = env["username"]
        return kwargs

    kwargs = {
        "socket_connect_timeout": socket_connect_timeout,
        "socket_timeout": socket_timeout,
        "decode_responses": decode_responses,
        "db": env["db"],
    }
    if health_check_interval:
        kwargs["health_check_interval"] = health_check_interval
    if max_connections is not None:
        kwargs["max_connections"] = max_connections
    if env.get("password"):
        kwargs["password"] = env["password"]
    if env.get("username"):
        kwargs["username"] = env["username"]
    if env.get("ssl"):
        kwargs["ssl"] = True
        kwargs["ssl_cert_reqs"] = env.get("ssl_cert_reqs", "required")
    return kwargs


def _create_standalone_client(
    env_prefix: str,
    decode_responses: bool,
    socket_connect_timeout: int,
    socket_timeout: int,
    max_connections: int | None,
    health_check_interval: int = 0,
    db_override: int | None = None,
) -> redis.Redis:
    env = _resolve_redis_env(env_prefix, default_port="6379", db_override=db_override)

    logger.info(
        "Redis standalone mode enabled. Connecting to %s:%s", env["host"], env["port"]
    )

    kwargs = _build_connection_kwargs(
        env,
        decode_responses,
        socket_connect_timeout,
        socket_timeout,
        health_check_interval=health_check_interval,
    )
    kwargs["host"] = env["host"]
    kwargs["port"] = env["port"]

    if max_connections is not None:
        pool = redis.ConnectionPool(max_connections=max_connections, **kwargs)
        return redis.Redis(connection_pool=pool)

    return redis.Redis(**kwargs)


def _create_sentinel_client(
    env_prefix: str,
    decode_responses: bool,
    socket_connect_timeout: int,
    socket_timeout: int,
    health_check_interval: int = 0,
    max_connections: int | None = None,
    db_override: int | None = None,
) -> redis.Redis:
    env = _resolve_redis_env(env_prefix, default_port="26379", db_override=db_override)
    master_name = os.getenv(
        f"{env_prefix}SENTINEL_MASTER_NAME", _DEFAULT_SENTINEL_MASTER_NAME
    )

    logger.info(
        "Redis Sentinel mode enabled. Connecting to sentinel at %s:%s, master: %s",
        env["host"],
        env["port"],
        master_name,
    )

    # When sentinel_kwargs is provided, redis-py does NOT inherit socket
    # timeouts from connection_kwargs, so we must include them explicitly
    sentinel_kwargs = _build_connection_kwargs(
        env,
        decode_responses,
        socket_connect_timeout,
        socket_timeout,
        include_auth_only=True,
    )
    master_kwargs = _build_connection_kwargs(
        env,
        decode_responses,
        socket_connect_timeout,
        socket_timeout,
        health_check_interval=health_check_interval,
        max_connections=max_connections,
    )

    return _connect_with_retry(env, master_name, sentinel_kwargs, master_kwargs)


def _connect_with_retry(
    env: dict[str, Any],
    master_name: str,
    sentinel_kwargs: dict[str, Any],
    master_kwargs: dict[str, Any],
) -> redis.Redis:
    """Attempt Sentinel connection with exponential backoff retry."""
    host, port = env["host"], env["port"]
    last_error: Exception | None = None

    for attempt in range(_SENTINEL_MAX_RETRIES):
        try:
            sentinel = Sentinel(
                [(host, port)],
                socket_connect_timeout=sentinel_kwargs["socket_connect_timeout"],
                socket_timeout=sentinel_kwargs["socket_timeout"],
                sentinel_kwargs=sentinel_kwargs,
            )
            client = sentinel.master_for(master_name, **master_kwargs)
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
            raise RedisSentinelConnectionError(
                f"Non-retriable error connecting to Redis Sentinel: {e}"
            ) from e

    raise RedisSentinelConnectionError(
        f"Failed to connect to Redis Sentinel after {_SENTINEL_MAX_RETRIES} retries "
        f"(~5 minutes).\n"
        f"Sentinel endpoint: {host}:{port}\n"
        f"Service: {master_name}\n"
        f"Check Sentinel availability, REDIS_HOST, REDIS_PORT, and "
        f"REDIS_SENTINEL_MODE configuration.\n"
        f"Last error: {last_error}"
    )


class RedisClient:
    """Wrapper around redis.Redis providing a consistent interface.

    Always instantiate via RedisClient.from_env(), which delegates to
    create_redis_client() and handles both Sentinel and standalone modes.
    """

    redis_client: redis.Redis

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
        """Create client from environment variables.

        Delegates to create_redis_client() which handles both
        Sentinel and standalone modes transparently.
        """
        instance = cls.__new__(cls)
        instance.redis_client = create_redis_client(
            env_prefix=env_prefix, decode_responses=True
        )
        return instance
