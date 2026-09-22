"""Connection configuration for the shared Redis client factory (UN-4123).

These tests build clients and inspect the resulting connection kwargs. Nothing
connects to a server: every property under test is decided at construction, which
is exactly where the bugs being locked down lived.

The recurring theme is that a MISCONFIGURED Redis client fails quietly. A missing
TLS flag is a plaintext socket against a TLS port; an ignored db override is reads
and writes against the wrong keyspace; an empty-string env var counts as "set" to
``os.getenv`` and shadows the fallback that would have supplied the real value.
None of those raise at import, so they are asserted here instead.
"""

import pytest
import redis

from unstract.core.cache.redis_client import (
    build_socketio_redis_url,
    create_redis_client,
)

_REDIS_ENV_MARKERS = ("REDIS_", "CACHE_REDIS_", "MANUAL_REVIEW_REDIS_")


@pytest.fixture(autouse=True)
def _clean_redis_env(monkeypatch):
    """Drop inherited REDIS_* so a developer's shell cannot change the outcome."""
    import os

    for key in list(os.environ):
        if any(marker in key for marker in _REDIS_ENV_MARKERS):
            monkeypatch.delenv(key, raising=False)


def _kwargs(client: redis.Redis) -> dict:
    return client.connection_pool.connection_kwargs


def _connection_class(client: redis.Redis) -> str:
    return client.connection_pool.connection_class.__name__


class TestDefaults:
    def test_no_env_is_plaintext_localhost_db0(self):
        """The in-cluster/local path: unchanged by everything else in this suite."""
        client = create_redis_client()
        assert _connection_class(client) == "Connection"
        assert _kwargs(client)["host"] == "localhost"
        assert _kwargs(client)["port"] == 6379
        assert _kwargs(client)["db"] == 0
        assert "ssl_cert_reqs" not in _kwargs(client)

    def test_health_check_is_on_by_default(self, monkeypatch):
        """Guards against a connection killed while idle.

        A managed Redis fails over during maintenance and reaps idle connections
        (Azure Cache at 10 minutes). Without a health check the pooled connection
        is only discovered dead when a real command fails on it.
        """
        assert _kwargs(create_redis_client())["health_check_interval"] == 30

        monkeypatch.setenv("REDIS_HEALTH_CHECK_INTERVAL", "0")
        # redis-py always populates this key; 0 is its "disabled" value.
        assert _kwargs(create_redis_client())["health_check_interval"] == 0

    def test_explicit_argument_beats_env(self, monkeypatch):
        monkeypatch.setenv("REDIS_HEALTH_CHECK_INTERVAL", "45")
        assert _kwargs(create_redis_client(health_check_interval=7))[
            "health_check_interval"
        ] == 7

    def test_unparseable_health_check_falls_back(self, monkeypatch):
        """A typo must not take the platform's Redis down."""
        monkeypatch.setenv("REDIS_HEALTH_CHECK_INTERVAL", "thirty")
        assert _kwargs(create_redis_client())["health_check_interval"] == 30


class TestDiscreteTLS:
    def test_ssl_selects_a_tls_connection(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "cache.internal")
        monkeypatch.setenv("REDIS_SSL", "true")
        client = create_redis_client()
        assert _connection_class(client) == "SSLConnection"
        assert _kwargs(client)["ssl_cert_reqs"] == "required"

    def test_pooled_tls_client_is_usable(self, monkeypatch):
        """Regression: TLS + max_connections used to fail on the FIRST COMMAND.

        ``ConnectionPool`` hands its kwargs to the connection class, and the plain
        ``Connection`` has no ``ssl`` parameter. Construction succeeded, the pool
        kept the non-TLS class, and the first command raised
        ``TypeError: AbstractConnection.__init__() got an unexpected keyword
        argument 'ssl'`` — so platform-service (max_connections=10) would have
        started healthy and broken on first use.
        """
        monkeypatch.setenv("REDIS_SSL", "true")
        client = create_redis_client(max_connections=10)
        pool = client.connection_pool
        assert _connection_class(client) == "SSLConnection"
        assert "ssl" not in _kwargs(client)
        # Instantiating the connection is the step that used to raise; redis-py
        # opens the socket lazily, so this stays offline.
        assert pool.connection_class(**pool.connection_kwargs) is not None

    def test_prefixed_client_inherits_the_global_ssl_flag(self, monkeypatch):
        """CACHE_REDIS_* and MANUAL_REVIEW_* must not need their own SSL flag.

        Before this fell back, enabling TLS platform-wide meant remembering every
        prefix, and a forgotten one is a plaintext client against a TLS port.
        """
        monkeypatch.setenv("REDIS_SSL", "true")
        for prefix in ("CACHE_REDIS_", "MANUAL_REVIEW_REDIS_"):
            assert _connection_class(create_redis_client(env_prefix=prefix)) == (
                "SSLConnection"
            )

    def test_prefix_can_still_override_the_global_flag(self, monkeypatch):
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("CACHE_REDIS_SSL", "false")
        assert _connection_class(create_redis_client(env_prefix="CACHE_REDIS_")) == (
            "Connection"
        )

    def test_ca_certs_reach_the_connection(self, monkeypatch):
        """Needed for Memorystore, whose CA is not in the system trust store."""
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CA_CERTS", "/etc/ssl/redis-ca.pem")
        assert _kwargs(create_redis_client())["ssl_ca_certs"] == "/etc/ssl/redis-ca.pem"

    def test_ca_certs_ignored_without_tls(self, monkeypatch):
        monkeypatch.setenv("REDIS_SSL_CA_CERTS", "/etc/ssl/redis-ca.pem")
        assert "ssl_ca_certs" not in _kwargs(create_redis_client())


class TestUrlMode:
    def test_rediss_scheme_turns_on_tls_without_a_flag(self, monkeypatch):
        monkeypatch.setenv(
            "REDIS_URL", "rediss://cache.example:6380/2?ssl_cert_reqs=required"
        )
        client = create_redis_client()
        assert _connection_class(client) == "SSLConnection"
        assert _kwargs(client)["ssl_cert_reqs"] == "required"
        assert _kwargs(client)["db"] == 2

    def test_plain_scheme_stays_plaintext(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://cache.example:6379")
        assert _connection_class(create_redis_client()) == "Connection"

    def test_password_is_url_decoded(self, monkeypatch):
        """Generated passwords contain @ / +, so they arrive percent-encoded."""
        monkeypatch.setenv("REDIS_URL", "rediss://:p%40ss%2Fword@cache.example:6380")
        assert _kwargs(create_redis_client())["password"] == "p@ss/word"

    def test_explicit_db_argument_beats_the_url_path(self, monkeypatch):
        """redis-py lets the URL path win over a ``db`` kwarg — silently.

        sdk1's metrics client asks for db=1 explicitly. Without stripping the path
        it would land in the URL's db instead, writing metrics into another
        service's keyspace with nothing to indicate it.
        """
        monkeypatch.setenv("REDIS_URL", "rediss://cache.example:6380/5")
        assert _kwargs(create_redis_client(db=1))["db"] == 1

    def test_url_db_applies_when_no_override_is_given(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "rediss://cache.example:6380/5")
        assert _kwargs(create_redis_client())["db"] == 5

    def test_url_takes_precedence_over_discrete_vars(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "in-cluster")
        monkeypatch.setenv("REDIS_URL", "redis://managed.example:6379")
        assert _kwargs(create_redis_client())["host"] == "managed.example"

    def test_prefixed_url_is_used_for_that_prefix_only(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://shared.example:6379")
        monkeypatch.setenv("CACHE_REDIS_URL", "redis://cache.example:6379")
        assert _kwargs(create_redis_client())["host"] == "shared.example"
        assert (
            _kwargs(create_redis_client(env_prefix="CACHE_REDIS_"))["host"]
            == "cache.example"
        )

    def test_ca_certs_apply_in_url_mode(self, monkeypatch):
        """Found by a live run against a TLS Redis, not by reading the code.

        URL mode carries TLS in the scheme and never sets REDIS_SSL, so while the
        CA was read only inside that flag's branch, `rediss://` verified against
        the system trust store alone — and failed for precisely the servers a CA
        is needed for (Memorystore's CA is not publicly trusted).
        """
        monkeypatch.setenv("REDIS_URL", "rediss://cache.example:6380/0")
        monkeypatch.setenv("REDIS_SSL_CA_CERTS", "/etc/ssl/redis-ca.pem")
        assert _kwargs(create_redis_client())["ssl_ca_certs"] == "/etc/ssl/redis-ca.pem"

    def test_ca_certs_ignored_for_a_plaintext_url(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://cache.example:6379/0")
        monkeypatch.setenv("REDIS_SSL_CA_CERTS", "/etc/ssl/redis-ca.pem")
        assert "ssl_ca_certs" not in _kwargs(create_redis_client())

    def test_prefix_db_wins_over_an_inherited_url(self, monkeypatch):
        """The Helm chart's shape: one REDIS_URL, plus CACHE_REDIS_DB=1.

        The cache prefix inherits the generic URL for its endpoint, but its own
        db must still apply — otherwise the worker cache silently moves to the
        URL's db and lands beside everything else on db 0.
        """
        monkeypatch.setenv("REDIS_URL", "rediss://cache.example:6380/0")
        monkeypatch.setenv("CACHE_REDIS_DB", "1")
        assert _kwargs(create_redis_client(env_prefix="CACHE_REDIS_"))["db"] == 1
        assert _kwargs(create_redis_client())["db"] == 0

    def test_an_explicit_prefix_url_keeps_its_own_db(self, monkeypatch):
        """A URL written FOR this prefix names its db deliberately."""
        monkeypatch.setenv("REDIS_URL", "rediss://cache.example:6380/0")
        monkeypatch.setenv("CACHE_REDIS_URL", "rediss://cache.example:6380/3")
        monkeypatch.setenv("CACHE_REDIS_DB", "1")
        assert _kwargs(create_redis_client(env_prefix="CACHE_REDIS_"))["db"] == 3

    def test_explicit_argument_still_wins(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "rediss://cache.example:6380/0")
        monkeypatch.setenv("CACHE_REDIS_DB", "1")
        assert _kwargs(create_redis_client(env_prefix="CACHE_REDIS_", db=7))["db"] == 7

    def test_pool_size_survives_url_mode(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "rediss://cache.example:6380")
        client = create_redis_client(max_connections=10)
        assert client.connection_pool.max_connections == 10
        assert _connection_class(client) == "SSLConnection"


class TestAuth:
    def test_password_only_auth_sends_no_username(self, monkeypatch):
        """Managed AUTH strings authenticate the built-in ``default`` user.

        Named ACL users are not supported platform-wide — django-redis discards
        the username — so an empty REDIS_USER must stay empty rather than
        defaulting to something that turns AUTH into its two-argument form.
        """
        monkeypatch.setenv("REDIS_PASSWORD", "s3cr3t")
        kwargs = _kwargs(create_redis_client())
        assert kwargs["password"] == "s3cr3t"
        assert kwargs.get("username") is None

    def test_prefixed_client_inherits_the_global_password(self, monkeypatch):
        monkeypatch.setenv("REDIS_PASSWORD", "s3cr3t")
        assert _kwargs(create_redis_client(env_prefix="CACHE_REDIS_"))["password"] == (
            "s3cr3t"
        )

    def test_empty_prefixed_password_shadows_the_fallback(self, monkeypatch):
        """Documents a trap rather than endorsing it.

        ``os.getenv(key, fallback)`` returns "" when the key exists but is empty,
        so an empty CACHE_REDIS_PASSWORD suppresses REDIS_PASSWORD and the client
        connects UNAUTHENTICATED. The Helm chart must therefore never render an
        empty credential; this test fails if that behaviour ever changes, so the
        chart-side guarantee can be revisited.
        """
        monkeypatch.setenv("REDIS_PASSWORD", "s3cr3t")
        monkeypatch.setenv("CACHE_REDIS_PASSWORD", "")
        kwargs = _kwargs(create_redis_client(env_prefix="CACHE_REDIS_"))
        assert kwargs.get("password") is None


class TestSocketIoUrl:
    """The URL kombu gets for Socket.IO (UN-4123).

    kombu takes a URL and nothing else, so every TLS setting has to survive in the
    query string. The backend and the log-consumer worker both publish through it;
    they each built this by hand until they drifted, so these cases pin what the
    shared builder must produce.
    """

    def test_plaintext_default(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "unstract-redis")
        assert build_socketio_redis_url() == "redis://unstract-redis:6379"

    def test_password_only_is_url_encoded(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_PASSWORD", "p@ss/word")
        assert build_socketio_redis_url() == "redis://:p%40ss%2Fword@h:6379"

    def test_tls_switches_scheme_and_pins_verification(self, monkeypatch):
        """kombu defaults rediss:// to CERT_NONE — encrypted but unauthenticated.

        Without ssl_cert_reqs in the query, enabling TLS would buy encryption
        against an unverified server, which is not what operators understand it
        to mean.
        """
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_SSL", "true")
        url = build_socketio_redis_url()
        assert url.startswith("rediss://")
        assert "ssl_cert_reqs=required" in url

    def test_ca_certs_travel_in_the_query(self, monkeypatch):
        """The Django cache gets the CA through pool kwargs; kombu has only this.

        Without it, cache access succeeds while the Socket.IO connection cannot
        verify the same server — so WebSocket delivery dies on its own.
        """
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CA_CERTS", "/etc/ssl/redis-ca.pem")
        assert "ssl_ca_certs=%2Fetc%2Fssl%2Fredis-ca.pem" in build_socketio_redis_url()

    def test_url_mode_is_used_as_given(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "in-cluster")
        monkeypatch.setenv("REDIS_URL", "redis://managed.example:6379/0")
        assert build_socketio_redis_url() == "redis://managed.example:6379/0"

    def test_a_tls_url_without_cert_reqs_gets_them(self, monkeypatch):
        """A rediss:// URL alone would leave kombu on CERT_NONE."""
        monkeypatch.setenv("REDIS_URL", "rediss://:pw@managed.example:6380/0")
        url = build_socketio_redis_url()
        assert "ssl_cert_reqs=required" in url

    def test_an_explicit_cert_reqs_in_the_url_is_respected(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "rediss://h:6380/0?ssl_cert_reqs=none")
        url = build_socketio_redis_url()
        assert "ssl_cert_reqs=none" in url
        assert url.count("ssl_cert_reqs") == 1

    def test_ca_is_added_to_a_tls_url(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "rediss://h:6380/0?ssl_cert_reqs=required")
        monkeypatch.setenv("REDIS_SSL_CA_CERTS", "/ca.pem")
        assert "ssl_ca_certs=%2Fca.pem" in build_socketio_redis_url()

    def test_a_plaintext_url_gains_no_tls_query(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
        monkeypatch.setenv("REDIS_SSL_CA_CERTS", "/ca.pem")
        assert build_socketio_redis_url() == "redis://h:6379/0"


class TestCertReqsAndHostname:
    """ssl_cert_reqs used to be resolved three different ways in one module.

    URL mode never read it, and a prefixed client had no fallback to the generic
    REDIS_SSL_CERT_REQS — so one process could hold two verification policies.
    """

    def test_prefix_inherits_the_generic_cert_reqs(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CERT_REQS", "none")
        for prefix in ("REDIS_", "CACHE_REDIS_", "MANUAL_REVIEW_REDIS_"):
            assert _kwargs(create_redis_client(env_prefix=prefix))["ssl_cert_reqs"] == (
                "none"
            ), prefix

    def test_url_mode_carries_cert_reqs(self, monkeypatch):
        """`rediss://` with no query used to take redis-py's default silently."""
        monkeypatch.setenv("REDIS_URL", "rediss://h:6380/0")
        monkeypatch.setenv("REDIS_SSL_CERT_REQS", "none")
        assert _kwargs(create_redis_client())["ssl_cert_reqs"] == "none"

    def test_a_cert_reqs_in_the_url_still_wins(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "rediss://h:6380/0?ssl_cert_reqs=required")
        monkeypatch.setenv("REDIS_SSL_CERT_REQS", "none")
        assert _kwargs(create_redis_client())["ssl_cert_reqs"] == "required"

    def test_hostname_verification_is_on_by_default(self, monkeypatch):
        """redis-py defaults this to False, which leaves TLS unauthenticated."""
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_SSL", "true")
        assert _kwargs(create_redis_client())["ssl_check_hostname"] is True

    def test_hostname_verification_is_on_in_url_mode_too(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "rediss://h:6380/0")
        assert _kwargs(create_redis_client())["ssl_check_hostname"] is True

    def test_hostname_verification_is_forced_off_without_verification(self, monkeypatch):
        """ssl raises if check_hostname is True while verify_mode is CERT_NONE."""
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CERT_REQS", "none")
        assert _kwargs(create_redis_client())["ssl_check_hostname"] is False

    def test_hostname_verification_can_be_turned_off(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CHECK_HOSTNAME", "false")
        assert _kwargs(create_redis_client())["ssl_check_hostname"] is False

    def test_socketio_url_carries_both(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_SSL", "true")
        url = build_socketio_redis_url()
        assert "ssl_cert_reqs=required" in url
        assert "ssl_check_hostname=true" in url
