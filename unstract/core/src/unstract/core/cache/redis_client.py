"""Redis Client with Sentinel HA Support

Dual-mode Redis configuration:
- Standalone mode: traditional redis.Redis() when REDIS_SENTINEL_MODE is absent/False
- Sentinel mode: Sentinel.master_for() when REDIS_SENTINEL_MODE=True

Mode is detected from {prefix}SENTINEL_MODE env var (LLMW pattern).

A full URL in {prefix}URL (falling back to REDIS_URL) overrides the discrete
host/port/credential vars, and `rediss://` turns on TLS by itself — the scheme is
the switch, so there is no separate "use TLS" flag to forget. Discrete vars remain
the default and primary path: they need no URL-encoding of passwords, and they are
what the Helm chart and every sample.env configure.
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
from urllib.parse import urlsplit, urlunsplit

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

# redis-py sends a PING before reusing a connection idle for longer than this, so a
# connection killed while parked (managed-Redis failover, an idle-connection reaper —
# Azure Cache closes at 10 minutes) is discovered and replaced by the health check
# rather than by the next real command failing. 30s is redis-py's own documented
# recommendation. 0 disables it, which is what every client except the two worker
# caches used before UN-4123.
_DEFAULT_HEALTH_CHECK_INTERVAL = 30


def _resolve_health_check_interval(env_prefix: str, explicit: int) -> int:
    """Explicit argument wins; otherwise env, otherwise the default above."""
    if explicit:
        return explicit
    raw = os.getenv(
        f"{env_prefix}HEALTH_CHECK_INTERVAL",
        os.getenv("REDIS_HEALTH_CHECK_INTERVAL", str(_DEFAULT_HEALTH_CHECK_INTERVAL)),
    )
    try:
        return max(int(raw), 0)
    except ValueError:
        logger.warning(
            "Invalid %sHEALTH_CHECK_INTERVAL=%r; using %s",
            env_prefix,
            raw,
            _DEFAULT_HEALTH_CHECK_INTERVAL,
        )
        return _DEFAULT_HEALTH_CHECK_INTERVAL


def _strip_url_db_path(url: str) -> str:
    """Drop the /<db> path from a Redis URL.

    redis-py resolves the db from the URL path and IGNORES a `db=` kwarg, so a
    caller that asks for a specific db (sdk1 metrics uses db=1) would silently get
    the URL's db instead. Stripping the path lets the explicit argument apply.
    """
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", parts.query, parts.fragment))


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
        health_check_interval: Proactive health check interval in seconds. 0 means
            "unset" and falls back to {env_prefix}HEALTH_CHECK_INTERVAL, then
            REDIS_HEALTH_CHECK_INTERVAL, then 30s; set that env to 0 to disable.
        db: Optional DB index override. Applied even when a URL carries its own
            db path, which redis-py would otherwise silently prefer.

    Returns:
        Configured redis.Redis client (standalone or Sentinel-backed).

    Raises:
        RedisSentinelConnectionError: After exhausting retries in Sentinel mode.
    """
    health_check_interval = _resolve_health_check_interval(
        env_prefix, health_check_interval
    )
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
    # Falls back to REDIS_SSL: before UN-4123 each prefix needed its own *_SSL, so
    # turning TLS on platform-wide meant remembering CACHE_REDIS_SSL and
    # MANUAL_REVIEW_REDIS_SSL too — and a missed one fails as a plaintext client
    # talking to a TLS port, not as a config error.
    ssl = (
        os.getenv(f"{env_prefix}SSL", os.getenv("REDIS_SSL", "false")).strip().lower()
        == "true"
    )
    result: dict[str, Any] = {
        "host": host,
        "port": port,
        "password": password,
        "username": username,
        "db": db,
        "ssl": ssl,
        # A full URL, when given, is authoritative for host/port/credentials/db and
        # carries TLS in its scheme (rediss://). Everything above stays the default
        # path, so an unset URL changes nothing.
        "url": os.getenv(f"{env_prefix}URL", os.getenv("REDIS_URL", "")).strip(),
    }
    # A prefix that INHERITS the generic REDIS_URL must still honour its own
    # {prefix}DB. The Helm chart sets CACHE_REDIS_DB=1 while configuring one
    # REDIS_URL for the platform; without this the worker cache would silently
    # follow the URL's db instead, landing on db 0 beside everything else. An
    # explicit {prefix}URL is left alone — it names its own db deliberately.
    own_url = os.getenv(f"{env_prefix}URL", "").strip()
    own_db = os.getenv(f"{env_prefix}DB", "").strip()
    if result["url"] and not own_url and own_db and db_override is None:
        result["db_from_prefix_env"] = int(own_db)
    # Read OUTSIDE the `if ssl` below: URL mode carries TLS in the scheme and never
    # sets {prefix}SSL, so gating the CA on that flag left `rediss://` verifying
    # against the system trust store alone — which fails for exactly the servers
    # that need a CA. Consumers decide whether it applies.
    #
    # Needed where the server's CA is not publicly trusted — notably Memorystore,
    # whose CA is Google-managed. ElastiCache and Azure chain to public CAs.
    ca_certs = os.getenv(
        f"{env_prefix}SSL_CA_CERTS", os.getenv("REDIS_SSL_CA_CERTS", "")
    ).strip()
    if ca_certs:
        result["ssl_ca_certs"] = ca_certs
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
        if env.get("ssl_ca_certs"):
            kwargs["ssl_ca_certs"] = env["ssl_ca_certs"]
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

    if env["url"]:
        return _create_client_from_url(
            url=env["url"],
            decode_responses=decode_responses,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
            max_connections=max_connections,
            health_check_interval=health_check_interval,
            db_override=(
                db_override if db_override is not None else env.get("db_from_prefix_env")
            ),
            ssl_ca_certs=env.get("ssl_ca_certs"),
        )

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
        pool_kwargs = dict(kwargs)
        # ConnectionPool hands its kwargs to the connection class, and the plain
        # Connection has no `ssl` parameter — passing it raises TypeError. TLS on a
        # POOLED client (platform-service sets max_connections) therefore has to be
        # selected by connection class, not by a flag.
        if pool_kwargs.pop("ssl", False):
            pool_kwargs["connection_class"] = redis.SSLConnection
        pool = redis.ConnectionPool(max_connections=max_connections, **pool_kwargs)
        return redis.Redis(connection_pool=pool)

    return redis.Redis(**kwargs)


def _create_client_from_url(
    url: str,
    decode_responses: bool,
    socket_connect_timeout: int,
    socket_timeout: int,
    max_connections: int | None,
    health_check_interval: int,
    db_override: int | None,
    ssl_ca_certs: str | None,
) -> redis.Redis:
    """Build a client from a full Redis URL.

    `rediss://` selects TLS on its own — redis-py picks SSLConnection from the
    scheme — so TLS needs no separate switch, and `redis://` behaves exactly as the
    discrete host/port path does. TLS verification is tuned in the URL itself, e.g.
    `?ssl_cert_reqs=required`.
    """
    kwargs: dict[str, Any] = {
        "decode_responses": decode_responses,
        "socket_connect_timeout": socket_connect_timeout,
        "socket_timeout": socket_timeout,
    }
    if health_check_interval:
        kwargs["health_check_interval"] = health_check_interval
    if max_connections is not None:
        kwargs["max_connections"] = max_connections
    if ssl_ca_certs and url.startswith("rediss://"):
        kwargs["ssl_ca_certs"] = ssl_ca_certs
    if db_override is not None:
        # The URL path wins over a db kwarg in redis-py, so it has to go.
        url = _strip_url_db_path(url)
        kwargs["db"] = db_override

    parts = urlsplit(url)
    logger.info(
        "Redis URL mode enabled. Connecting to %s:%s (tls=%s)",
        parts.hostname,
        parts.port,
        parts.scheme == "rediss",
    )
    return redis.Redis.from_url(url, **kwargs)


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
