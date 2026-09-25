"""Redis Client with Sentinel HA Support

Dual-mode Redis configuration:
- Standalone mode: traditional redis.Redis() when REDIS_SENTINEL_MODE is absent/False
- Sentinel mode: Sentinel.master_for() when REDIS_SENTINEL_MODE=True

Mode is detected from {prefix}SENTINEL_MODE env var (LLMW pattern).

A full URL in {prefix}URL (falling back to REDIS_URL) overrides the discrete
host/port/credential vars, and `rediss://` turns on TLS by itself — the scheme is
the switch, so there is no separate "use TLS" flag to forget.

Precedence, in one sentence, in STANDALONE mode: a URL supplies host, port and
credentials; the database is the db var at the URL's own level — {prefix}DB for a
{prefix}URL, {prefix}DB or REDIS_DB for an inherited REDIS_URL — when explicitly
set, otherwise the URL's path, otherwise 0. An explicit `db=` argument beats all
of them. Discrete vars remain the default and primary path: they need no
URL-encoding of passwords, and they are what the Helm chart and every sample.env
configure.

Two deliberate exceptions to that sentence, both easy to trip over:
- Sentinel mode IGNORES {prefix}URL entirely and uses the discrete host/port; a
  Sentinel endpoint is a set of nodes, not one URL.
- build_socketio_redis_url carries no /db path, so a Socket.IO client built from
  discrete vars is on db 0 whatever {prefix}DB says. kombu keys are ephemeral
  pub/sub channels, so nothing is stored there to end up in the wrong database.
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
from urllib.parse import parse_qs, quote, urlencode, urlsplit, urlunsplit

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

# The scheme IS the TLS switch: redis-py, kombu and django-redis all select an
# SSL connection from it, which is why nothing here has a separate "use TLS" flag
# for URL mode.
_TLS_SCHEME = "rediss://"

# The three values redis-py accepts for ssl_cert_reqs. Anything else reaches
# redis-py as `RedisError: Invalid SSL Certificate Requirements Flag:` at the
# first command, so it is validated here where the variable name is still known.
_CERT_REQS_VALUES = frozenset({"none", "optional", "required"})
_DEFAULT_CERT_REQS = "required"

# Accepted spellings for the boolean env vars. A bare `== "true"` silently reads
# `1` and `yes` as FALSE, which for ssl_check_hostname means downgrading to an
# unauthenticated connection without a word in the log.
_TRUE_LITERALS = frozenset({"true", "1", "yes", "on"})
_FALSE_LITERALS = frozenset({"false", "0", "no", "off"})

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


def set_url_db_path(url: str, db: int) -> str:
    """Rewrite a Redis URL's /<db> path to `db`.

    The one place the database rule is applied to a URL. The backend's Django
    cache needs it too — django-redis takes a LOCATION string and ignores
    OPTIONS["DB"], so the only way to move that cache off the URL's own database
    is to rewrite the path — and if it re-implemented the rewrite, the backend
    and the workers would resolve the same REDIS_URL + REDIS_DB to DIFFERENT
    databases. They did: the backend followed the URL's path while
    create_redis_client honoured REDIS_DB, so workers RPUSHed log_history_queue
    to db N and the backend LPOPped an empty db 0, silently.
    """
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{db}", parts.query, parts.fragment))


def url_db_path(url: str) -> int | None:
    """The database a URL's path selects, or None when it carries no path."""
    path = urlsplit(url).path.strip("/")
    if not path:
        return None
    try:
        return int(path)
    except ValueError:
        return None


def _parse_bool(raw: str, default: bool, name: str) -> bool:
    """Parse a boolean env var; blank means UNSET, unknown warns and defaults.

    Blank-means-unset is this repo's own convention — `FOO=` in a sample.env
    means "leave the default", and every other variable in UN-4123 treats it that
    way. `os.getenv` does not: it reports an empty string as SET, so a bare
    `os.getenv(...) == "true"` turns `FOO=` into False.
    """
    value = raw.strip().lower()
    if not value:
        return default
    if value in _TRUE_LITERALS:
        return True
    if value in _FALSE_LITERALS:
        return False
    logger.warning("Invalid %s=%r; using %s", name, raw, default)
    return default


def parse_db(raw: str, env_prefix: str) -> int:
    """Parse a database index; blank means UNSET, unparseable warns and uses 0.

    Public because the backend reads database vars of its own — the cache db, the
    Sentinel branch's db, and FILE_ACTIVE_CACHE_REDIS_DB. Left to `int()` there,
    the two halves disagree on a malformed value: the workers warn and continue on
    db 0 while the backend refuses to start.

    A bare `int(os.getenv(...))` raised `ValueError: invalid literal for int()
    with base 10: ''` on `REDIS_DB=` — the blank-means-unset spelling used
    everywhere else in this work — out of create_redis_client, killing the
    process at import in most consumers and degrading to no-cache / no-metrics in
    the two that catch broadly. The message named neither the variable nor the
    prefix.
    """
    value = raw.strip()
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid %sDB=%r; using 0", env_prefix, raw)
        return 0


def resolve_ssl_cert_reqs(env_prefix: str = "REDIS_") -> str:
    """{prefix}SSL_CERT_REQS, falling back to REDIS_SSL_CERT_REQS, then "required".

    Normalised and validated in ONE place because the raw value used to reach
    three consumers that disagreed about it. A blank value gave a hard
    `RedisError` on the discrete client, a silent CERT_NONE on the kombu URL
    (kombu's own rediss:// default) and "required" on the URL path — one
    endpoint, three verification policies. Case and stray whitespace had the same
    effect, since the "is verification off?" test is an equality check.
    """
    raw = os.getenv(
        f"{env_prefix}SSL_CERT_REQS", os.getenv("REDIS_SSL_CERT_REQS", "")
    ).strip()
    value = raw.lower()
    if not value:
        return _DEFAULT_CERT_REQS
    if value not in _CERT_REQS_VALUES:
        logger.warning(
            "Invalid %sSSL_CERT_REQS=%r; expected one of %s. Using %s.",
            env_prefix,
            raw,
            ", ".join(sorted(_CERT_REQS_VALUES)),
            _DEFAULT_CERT_REQS,
        )
        return _DEFAULT_CERT_REQS
    return value


def resolve_ssl_check_hostname(env_prefix: str = "REDIS_", default: bool = True) -> bool:
    """{prefix}SSL_CHECK_HOSTNAME, falling back to REDIS_SSL_CHECK_HOSTNAME, then on.

    Exported so the backend's settings module uses the same parse rather than
    its own `== "true"`, which read a blank value — and `1`, and `yes` — as
    FALSE, silently downgrading the Django cache to an encrypted but
    unauthenticated connection.
    """
    return _parse_bool(
        os.getenv(
            f"{env_prefix}SSL_CHECK_HOSTNAME", os.getenv("REDIS_SSL_CHECK_HOSTNAME", "")
        ),
        default,
        f"{env_prefix}SSL_CHECK_HOSTNAME",
    )


def url_cert_reqs(url: str) -> str | None:
    """The ssl_cert_reqs already in a URL's query string, or None.

    The env var is NOT the whole answer: `?ssl_cert_reqs=none` in the URL is a
    documented form (docker/redis-tls/README.md), and it is what redis-py, kombu
    and django-redis all actually honour. Deciding "is verification off?" from
    the env var alone appended ssl_check_hostname=true beside a URL-borne
    CERT_NONE, and Python's ssl module refuses that combination — every
    connection in the process raised ValueError at first use.

    Takes the FIRST value on a repeat, matching redis-py's own parse_url.
    """
    if not url:
        return None
    values = parse_qs(urlsplit(url).query).get("ssl_cert_reqs")
    if not values:
        return None
    return values[0].strip().lower()


def effective_cert_reqs(url: str, env_cert_reqs: str) -> str:
    """What the connection will ACTUALLY use: the URL's query, else the env value."""
    return url_cert_reqs(url) or env_cert_reqs


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


def ensure_tls_query_params(
    url: str,
    cert_reqs: str | None = None,
    ca_certs: str | None = None,
    check_hostname: bool | None = None,
) -> str:
    """Add the TLS settings a `rediss://` URL is missing, leaving present ones alone.

    Anything that hands a URL to a library that reads TLS out of the query string
    needs this: kombu's KombuManager takes a URL and NOTHING else, and
    django-redis's LOCATION is a string too (it also reads
    OPTIONS["CONNECTION_POOL_KWARGS"], but the query string wins on conflict).

    It lives here rather than at each call site because a hand-rolled append at
    each one WOULD drift: teach one side ssl_cert_reqs and leave the other on
    ssl_ca_certs alone, and the same endpoint holds two verification policies
    depending on which side built the string.

    A non-TLS URL is returned untouched — there is nothing to configure.
    """
    if not url.startswith(_TLS_SCHEME):
        return url
    # What the URL already says beats what the caller resolved from the env. The
    # suppression below used to test the CALLER's cert_reqs, so a URL carrying
    # ?ssl_cert_reqs=none still got ssl_check_hostname=true appended, and Python's
    # ssl module raises on that pair — every connection, on a URL form this repo
    # documents as supported.
    active_cert_reqs = url_cert_reqs(url) or cert_reqs
    extra: dict[str, str] = {}
    if cert_reqs and "ssl_cert_reqs=" not in url:
        extra["ssl_cert_reqs"] = cert_reqs
    if (
        check_hostname is not None
        and "ssl_check_hostname=" not in url
        and active_cert_reqs != "none"
    ):
        # A chain verified against a public CA says nothing about WHICH server
        # answered unless the hostname is checked.
        extra["ssl_check_hostname"] = str(check_hostname).lower()
    if ca_certs and "ssl_ca_certs=" not in url:
        extra["ssl_ca_certs"] = ca_certs
    if not extra:
        return url
    separator = "&" if "?" in url else "?"
    # safe="/" keeps a CA path readable: a slash is legal in a query value, and
    # percent-encoding it only makes the URL harder to eyeball in a log line.
    return url + separator + urlencode(extra, safe="/", quote_via=quote)


def _compose_redis_url(env: dict[str, Any]) -> str:
    """Assemble a URL from the discrete vars, percent-encoding the credentials.

    Split out of build_socketio_redis_url so that function stays about the TLS
    query string rather than also being a URL builder.
    """
    credentials = ""
    if env.get("username") and env.get("password"):
        credentials = (
            f"{quote(str(env['username']), safe='')}:"
            f"{quote(str(env['password']), safe='')}@"
        )
    elif env.get("password"):
        credentials = f":{quote(str(env['password']), safe='')}@"
    scheme = "rediss" if env.get("ssl") else "redis"
    return f"{scheme}://{credentials}{env['host']}:{env['port']}"


def apply_url_credentials(url: str, password: str | None, username: str | None) -> str:
    """Put credentials into a URL that carries none, leaving one that does alone.

    kombu takes a URL and NOTHING else — no connection kwargs — so a password
    supplied separately cannot reach it any other way. A URL written without
    credentials would otherwise produce an anonymous publisher against an
    authenticated server, and the Socket.IO events simply stop arriving.

    The password IS in the returned string, unavoidably. That is acceptable here
    and not in a values file: this URL is built in-process and handed straight to
    the client, rather than written into a manifest, a Secret template or an
    error message.
    """
    if not password:
        return url
    parts = urlsplit(url)
    if parts.password is not None:
        return url
    username = parts.username or username
    credentials = f"{quote(str(username), safe='')}:" if username else ":"
    credentials += f"{quote(str(password), safe='')}@"
    return urlunsplit(
        (
            parts.scheme,
            credentials + parts.netloc,
            parts.path,
            parts.query,
            parts.fragment,
        )
    )


def build_socketio_redis_url(env_prefix: str = "REDIS_") -> str:
    """Redis URL for a Socket.IO/kombu client, TLS settings included (UN-4123).

    The backend and the log-consumer worker both publish Socket.IO events through
    kombu, and each built this URL by hand. Two hand-built URLs for one endpoint
    drift: teach one of them TLS and the other keeps its ``redis://``, and against
    a TLS-only endpoint that publisher simply cannot connect — no exception the
    caller sees, just execution logs that stop reaching the UI. One builder serves
    both so the pair cannot diverge.

    kombu reads TLS out of the URL and NOTHING ELSE: ``KombuManager`` takes a URL,
    not connection kwargs. Two consequences are handled here rather than left to
    each caller:

    * ``ssl_cert_reqs`` must be in the query string. Kombu defaults a ``rediss://``
      URL to ``CERT_NONE`` — encrypted, but the server is never authenticated,
      which is not what enabling TLS is understood to buy.
    * ``ssl_ca_certs`` must be there too, or a privately-signed server (Memorystore)
      fails verification even though the Django cache beside it succeeds.

    Sentinel is deliberately out of scope HERE: it is the self-hosted HA path, its
    URL has a different shape, and a managed endpoint is a single primary. (The
    Sentinel CLIENT does get TLS, on both the discovery and master connections —
    see _build_connection_kwargs; it is only this URL builder that does not.)
    """
    env = _resolve_redis_env(env_prefix)
    # _resolve_redis_env always populates this now, normalised and validated.
    # The `or os.getenv(...)` fallback that used to sit here re-stated the same
    # resolution chain and could only fire on a blank value — which it then
    # re-read as blank, producing a URL with NO ssl_cert_reqs and letting kombu
    # apply its rediss:// default of CERT_NONE.
    cert_reqs = env["ssl_cert_reqs"]
    ca_certs = env.get("ssl_ca_certs")

    url = env["url"] or _compose_redis_url(env)
    # _compose_redis_url already embeds them for the discrete path; a configured
    # URL may not carry any, and kombu can read them from nowhere else.
    url = apply_url_credentials(url, env.get("url_password"), env.get("url_username"))
    if not url.startswith(_TLS_SCHEME):
        return url

    url = ensure_tls_query_params(
        url,
        cert_reqs=cert_reqs,
        ca_certs=ca_certs,
        check_hostname=env.get("ssl_check_hostname", True),
    )
    return url


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
    prefixed_db = os.getenv(f"{env_prefix}DB", "").strip()
    generic_db = os.getenv("REDIS_DB", "").strip()
    db = (
        db_override
        if db_override is not None
        else parse_db(prefixed_db or generic_db, env_prefix)
    )
    # Falls back to REDIS_SSL: before UN-4123 each prefix needed its own *_SSL, so
    # turning TLS on platform-wide meant remembering CACHE_REDIS_SSL and
    # MANUAL_REVIEW_REDIS_SSL too — and a missed one fails as a plaintext client
    # talking to a TLS port, not as a config error.
    ssl = (
        os.getenv(f"{env_prefix}SSL", os.getenv("REDIS_SSL", "false")).strip().lower()
        == "true"
    )
    own_url = os.getenv(f"{env_prefix}URL", "").strip()
    generic_url = os.getenv("REDIS_URL", "").strip()
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
        "url": own_url or generic_url,
    }
    # A URL's scheme is authoritative and silently wins over {prefix}SSL, so say
    # so out loud: an operator who turns REDIS_SSL on while an older plaintext
    # REDIS_URL is still set gets cleartext on the wire believing TLS is on. The
    # mismatch is never deliberate — a URL that means TLS says rediss://.
    if result["url"] and ssl and not result["url"].startswith(_TLS_SCHEME):
        logger.error(
            "%sSSL is true but %sURL uses a plaintext scheme; the URL wins, so this "
            "connection will NOT be encrypted. Use rediss:// in the URL, or clear it "
            "to use the discrete host/port vars.",
            env_prefix,
            env_prefix,
        )
    # THE DATABASE RULE, in one sentence: a URL supplies host, port and
    # credentials; the database is the db var AT THE URL'S OWN LEVEL when that is
    # explicitly set, otherwise the URL's path, otherwise 0.
    #
    # It has to be stated because redis-py's own rule is different — the URL path
    # wins and a db= kwarg is ignored — and because the two halves used to
    # disagree with each other. An INHERITED generic URL honoured the prefix's db
    # (the chart sets one REDIS_URL and CACHE_REDIS_DB=1, and without this the
    # worker cache silently joined everything else on db 0), while a prefix's OWN
    # url did not: an explicit REDIS_DB beside REDIS_URL was dropped, and beside a
    # URL carrying no path at all the db came out as None rather than 0.
    #
    # "At the URL's own level" is what keeps the generic REDIS_DB from reaching
    # across into a prefix that brought its own URL. workers/sample.env ships
    # REDIS_DB=0 uncommented, so a plain `os.getenv({prefix}DB, os.getenv(REDIS_DB))`
    # meant CACHE_REDIS_URL=rediss://…/1 landed on db 0 — an unrelated global
    # silently overriding the path the operator wrote, which is not the rule the
    # docstring, sample.env or the chart state. For env_prefix="REDIS_" the two
    # levels are the same variable, so this reads identically there.
    explicit_db = prefixed_db if own_url else (prefixed_db or generic_db)
    # CREDENTIALS AT THE URL'S OWN LEVEL, by the same rule as the database above.
    # A prefix that brought its OWN url may point at a DIFFERENT endpoint, and
    # an anonymous one at that; letting the generic REDIS_PASSWORD reach across
    # would make that client send AUTH to a server with none, breaking a
    # connection that worked before. An INHERITED url is the same endpoint as
    # the generic one, so the full fallback chain applies. For env_prefix
    # "REDIS_" the two levels are the same variable and this reads identically.
    if own_url:
        result["url_password"] = os.getenv(f"{env_prefix}PASSWORD")
        result["url_username"] = os.getenv(
            f"{env_prefix}USER", os.getenv(f"{env_prefix}USERNAME")
        )
    else:
        result["url_password"] = result["password"]
        result["url_username"] = result["username"]
    if result["url"] and explicit_db and db_override is None:
        result["db_from_prefix_env"] = parse_db(explicit_db, env_prefix)
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
    # Resolved OUTSIDE the ssl gate and WITH the generic fallback, for the same
    # reason as ssl_ca_certs above. Gated on `if ssl`, URL mode would never set it
    # at all — `rediss://` silently taking redis-py's default while the Socket.IO
    # URL beside it carried the operator's value, one process holding two
    # verification policies. The generic fallback closes a second gap that IS in
    # shipped code: before UN-4123 a prefixed client ignored REDIS_SSL_CERT_REQS,
    # so CACHE_REDIS_ stayed on "required" while REDIS_ honoured "none", and the
    # worker cache alone failed verification and degraded to no-cache with only a
    # warning.
    result["ssl_cert_reqs"] = resolve_ssl_cert_reqs(env_prefix)
    # Hostname verification. redis-py defaults ssl_check_hostname to FALSE and
    # overrides ssl.create_default_context()'s safe default with it, so a verified
    # chain still proves nothing about WHICH server answered: against a publicly
    # trusted CA — the ElastiCache/Azure case — any valid certificate for any
    # domain is accepted, and an on-path attacker can terminate the connection.
    # Encryption without server authentication is not what enabling TLS is
    # understood to buy, which is the same argument this module already makes for
    # kombu's CERT_NONE default.
    #
    # Forced off when verification itself is off: Python's ssl module raises if
    # check_hostname is True while verify_mode is CERT_NONE. Decided from the
    # EFFECTIVE value — the URL's query string outranks the env var, and testing
    # the env var alone is what produced that ValueError on every connection.
    raw_check_hostname = os.getenv(
        f"{env_prefix}SSL_CHECK_HOSTNAME", os.getenv("REDIS_SSL_CHECK_HOSTNAME", "")
    )
    # Whether the operator ASKED for a value, as opposed to inheriting the
    # default. Sentinel's master plane needs to know the difference — see
    # _tls_kwargs. A value that does not parse is NOT a request: it warns and
    # falls back, so treating it as explicit would let a typo turn hostname
    # verification back on for Sentinel masters, which is the breakage this
    # distinction exists to avoid.
    result["ssl_check_hostname_explicit"] = (
        raw_check_hostname.strip().lower() in _TRUE_LITERALS | _FALSE_LITERALS
    )
    if effective_cert_reqs(result["url"], result["ssl_cert_reqs"]) == "none":
        result["ssl_check_hostname"] = False
        result["ssl_check_hostname_explicit"] = False
    else:
        result["ssl_check_hostname"] = resolve_ssl_check_hostname(env_prefix)
    return result


def _tls_kwargs(env: dict[str, Any], sentinel_master: bool = False) -> dict[str, Any]:
    """TLS connection kwargs, empty when TLS is off.

    Shared by BOTH branches of _build_connection_kwargs on purpose. The auth-only
    branch builds Sentinel's DISCOVERY connections, and it used to return before
    the TLS block below — so the master connection was encrypted while the
    Sentinel password went out in clear against a Sentinel that still accepted
    plaintext, and a TLS-only Sentinel failed through the full ten-attempt backoff
    instead. One helper means the two cannot drift again.

    Sentinel and master share a certificate in every deployment that enables TLS —
    a Sentinel node IS a redis-server and takes the same tls-port configuration —
    so this follows {prefix}SSL rather than adding a switch of its own.

    Args:
        sentinel_master: True for a Sentinel-managed MASTER connection. Those
            connect to whatever `SENTINEL get-master-addr-by-name` returns, and
            SentinelManagedConnection assigns that address straight to
            ``self.host`` — which SSLConnection then passes as ``server_hostname``.
            It is an IP, so hostname verification is checked against an IP that
            no DNS SAN covers, and pinning an IP SAN is not a workable answer
            because the address changes on failover. Turning hostname
            verification on by default would therefore have broken every existing
            REDIS_SENTINEL_MODE + REDIS_SSL deployment on upgrade, failing
            through the full ten-attempt backoff at startup. An operator who sets
            {prefix}SSL_CHECK_HOSTNAME explicitly still gets what they asked for.
    """
    if not env.get("ssl"):
        return {}
    check_hostname = env.get("ssl_check_hostname", True)
    if sentinel_master and not env.get("ssl_check_hostname_explicit"):
        check_hostname = False
    kwargs: dict[str, Any] = {
        "ssl": True,
        "ssl_cert_reqs": env.get("ssl_cert_reqs", _DEFAULT_CERT_REQS),
        "ssl_check_hostname": check_hostname,
    }
    if env.get("ssl_ca_certs"):
        kwargs["ssl_ca_certs"] = env["ssl_ca_certs"]
    return kwargs


def _build_connection_kwargs(
    env: dict[str, Any],
    decode_responses: bool,
    socket_connect_timeout: int,
    socket_timeout: int,
    health_check_interval: int = 0,
    max_connections: int | None = None,
    include_auth_only: bool = False,
    sentinel_master: bool = False,
) -> dict[str, Any]:
    """Build kwargs dict for Redis/Sentinel connections.

    Args:
        include_auth_only: If True, omit the master-connection kwargs (db,
            decode_responses, pool sizing) and return only what Sentinel's
            DISCOVERY connections need: timeouts, credentials and TLS.
        sentinel_master: True when these kwargs configure a Sentinel-managed
            master connection rather than a standalone one. Only affects
            hostname verification — see _tls_kwargs.
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
        # The DISCOVERY connections get TLS too — see _tls_kwargs.
        kwargs.update(_tls_kwargs(env))
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
    kwargs.update(_tls_kwargs(env, sentinel_master=sentinel_master))
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
            ssl_cert_reqs=env.get("ssl_cert_reqs"),
            ssl_check_hostname=env.get("ssl_check_hostname"),
            password=env.get("url_password"),
            username=env.get("url_username"),
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
    ssl_cert_reqs: str | None = None,
    ssl_check_hostname: bool | None = None,
    password: str | None = None,
    username: str | None = None,
) -> redis.Redis:
    """Build a client from a full Redis URL.

    `rediss://` selects TLS on its own — redis-py picks SSLConnection from the
    scheme — so TLS needs no separate switch, and `redis://` behaves exactly as the
    discrete host/port path does. TLS verification is tuned in the URL itself, e.g.
    `?ssl_cert_reqs=required`, or by {prefix}SSL_CERT_REQS /
    {prefix}SSL_CHECK_HOSTNAME, which fill in only where the URL's query string is
    silent — the route docker/redis-tls/README.md recommends for the dev recipe.
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
    if url.startswith(_TLS_SCHEME):
        # Set explicitly, or `rediss://` takes redis-py's defaults: verification
        # policy diverging from the discrete path within one process, and hostname
        # checking off. A setting already in the URL's query string wins; these
        # only fill the gap.
        if ssl_ca_certs:
            kwargs["ssl_ca_certs"] = ssl_ca_certs
        if "ssl_cert_reqs=" not in url and ssl_cert_reqs:
            kwargs["ssl_cert_reqs"] = ssl_cert_reqs
        # Suppressed when verification is off, decided from what the URL ACTUALLY
        # carries rather than from the env value: a URL saying ssl_cert_reqs=none
        # with the env at its "required" default used to get check_hostname=True
        # bolted on, and ssl.SSLContext refuses that pair — ValueError on the
        # first command, on every client in the process.
        if (
            "ssl_check_hostname=" not in url
            and ssl_check_hostname is not None
            and effective_cert_reqs(url, ssl_cert_reqs or _DEFAULT_CERT_REQS) != "none"
        ):
            kwargs["ssl_check_hostname"] = ssl_check_hostname
    if db_override is not None:
        # The URL path wins over a db kwarg in redis-py, so it has to go.
        url = _strip_url_db_path(url)
        kwargs["db"] = db_override

    parts = urlsplit(url)
    # Credentials FILL A GAP the URL leaves; they never override one.
    # ConnectionPool.from_url ends with kwargs.update(url_options), so a URL
    # carrying credentials still wins.
    #
    # Without this, a URL written WITHOUT credentials plus a separately
    # configured {prefix}PASSWORD connected ANONYMOUSLY — and setting the two
    # apart is the configuration the on-prem recipe should be able to recommend,
    # because it keeps the password out of a URL that gets printed into error
    # messages, ArgoCD conditions and ExternalSecret templates. The endpoint
    # answers NOAUTH on the first command, which reads as a broken server rather
    # than a dropped password.
    # Gated on the PASSWORD, and the username rides with it. A username alone is
    # not a credential: values.yaml ships REDIS_USER: default, so filling it in
    # on its own would make redis-py send AUTH to the in-cluster server, which
    # has none — turning a working default deployment into a failing one.
    # Keyed on the URL's PASSWORD, not on the presence of "@". A URL may carry an
    # ACL username alone — redis://alice@host — and that @ is not evidence of a
    # password; treating it as such dropped the separately supplied one and left
    # the client unable to authenticate.
    if password and parts.password is None:
        kwargs["password"] = password
        if username and not parts.username:
            kwargs["username"] = username
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
        sentinel_master=True,
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
