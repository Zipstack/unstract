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

import logging
import pathlib
import re
from urllib.parse import unquote, urlsplit

import pytest
import redis
from unstract.core.cache.redis_client import (
    url_username_from_env,
    parse_port,
    env_chain_named,
    env_chain,
    _build_connection_kwargs,
    _resolve_redis_env,
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
        assert (
            _kwargs(create_redis_client(health_check_interval=7))["health_check_interval"]
            == 7
        )

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

    def test_an_explicit_db_beats_even_this_prefixs_own_url(self, monkeypatch):
        """Changed deliberately: {prefix}DB wins over ANY url's path.

        This used to assert 3 — a URL written for this prefix kept its own db,
        while an INHERITED url lost to {prefix}DB. Two rules for one question, and
        no way to state either without naming which url it came from. The uniform
        rule is: a url supplies host/port/credentials, {prefix}DB supplies the
        database when set. An operator who wants the url's db simply leaves
        {prefix}DB unset, which is covered by the case above.
        """
        monkeypatch.setenv("REDIS_URL", "rediss://cache.example:6380/0")
        monkeypatch.setenv("CACHE_REDIS_URL", "rediss://cache.example:6380/3")
        monkeypatch.setenv("CACHE_REDIS_DB", "1")
        assert _kwargs(create_redis_client(env_prefix="CACHE_REDIS_"))["db"] == 1

    def test_a_prefix_url_path_applies_when_no_db_is_set(self, monkeypatch):
        monkeypatch.setenv("CACHE_REDIS_URL", "rediss://cache.example:6380/3")
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

    def test_empty_prefixed_password_falls_through_to_the_fallback(self, monkeypatch):
        """This is the revisit the previous version of this test asked for.

        It used to assert the opposite and said so: an empty
        CACHE_REDIS_PASSWORD suppressed REDIS_PASSWORD and the client connected
        UNAUTHENTICATED, which was tolerated because "the Helm chart must
        therefore never render an empty credential".

        That guarantee does not hold. workers/sample.env ships
        `CACHE_REDIS_PASSWORD=` uncommented, so an operator following this
        module's own managed-Redis recipe — REDIS_URL without credentials plus
        REDIS_PASSWORD — got no password on any prefixed client and a NOAUTH on
        first command. Blank now means unset here, the same rule parse_db and
        _parse_bool already document two functions away.
        """
        monkeypatch.setenv("REDIS_PASSWORD", "s3cr3t")
        monkeypatch.setenv("CACHE_REDIS_PASSWORD", "")
        kwargs = _kwargs(create_redis_client(env_prefix="CACHE_REDIS_"))
        assert kwargs["password"] == "s3cr3t"

    def test_a_prefixed_password_still_overrides(self, monkeypatch):
        """Blank falling through must not turn into the prefix being ignored."""
        monkeypatch.setenv("REDIS_PASSWORD", "s3cr3t")
        monkeypatch.setenv("CACHE_REDIS_PASSWORD", "other")
        kwargs = _kwargs(create_redis_client(env_prefix="CACHE_REDIS_"))
        assert kwargs["password"] == "other"

    def test_a_blank_password_on_a_prefixed_url_reaches_the_url(self, monkeypatch):
        """The recipe this PR documents, with the sample.env blank in place."""
        monkeypatch.setenv("REDIS_URL", "rediss://managed:6380/0")
        monkeypatch.setenv("REDIS_PASSWORD", "pw")
        monkeypatch.setenv("CACHE_REDIS_PASSWORD", "")
        assert urlsplit(build_socketio_redis_url("CACHE_REDIS_")).password == "pw"


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
        """Kombu defaults rediss:// to CERT_NONE — encrypted but unauthenticated.

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
        assert "ssl_ca_certs=/etc/ssl/redis-ca.pem" in build_socketio_redis_url()

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
        assert "ssl_ca_certs=/ca.pem" in build_socketio_redis_url()

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
        """Ssl raises if check_hostname is True while verify_mode is CERT_NONE."""
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


class TestSentinelTls:
    """Sentinel's DISCOVERY connections used to stay plaintext under REDIS_SSL.

    redis-py builds the Sentinel clients from sentinel_kwargs alone, so the master
    connection was encrypted while the Sentinel password went out in clear — one
    switch, two answers.
    """

    def _clients(self, monkeypatch):
        from redis.sentinel import Sentinel

        monkeypatch.setenv("REDIS_HOST", "sentinel-svc")
        monkeypatch.setenv("REDIS_PORT", "26379")
        monkeypatch.setenv("REDIS_PASSWORD", "pw")
        env = _resolve_redis_env("REDIS_", default_port="26379")
        sentinel = Sentinel(
            [("sentinel-svc", 26379)],
            sentinel_kwargs=_build_connection_kwargs(
                env, True, 5, 5, include_auth_only=True
            ),
        )
        master = sentinel.master_for(
            "mymaster", **_build_connection_kwargs(env, True, 5, 5)
        )
        return sentinel, master

    def test_tls_reaches_both_planes(self, monkeypatch):
        monkeypatch.setenv("REDIS_SSL", "true")
        sentinel, master = self._clients(monkeypatch)
        assert (
            sentinel.sentinels[0].connection_pool.connection_class.__name__
            == "SSLConnection"
        )
        assert (
            master.connection_pool.connection_class.__name__
            == "SentinelManagedSSLConnection"
        )

    def test_plaintext_sentinel_is_unchanged(self, monkeypatch):
        sentinel, master = self._clients(monkeypatch)
        assert (
            sentinel.sentinels[0].connection_pool.connection_class.__name__
            == "Connection"
        )
        assert (
            master.connection_pool.connection_class.__name__
            == "SentinelManagedConnection"
        )


class TestDatabaseRule:
    """A URL supplies host/port/credentials; the db is {prefix}DB if explicitly
    set, else the URL's path, else 0.

    The two halves used to disagree: an INHERITED generic URL honoured the
    prefix's db, while a prefix's OWN url did not — an explicit REDIS_DB beside
    REDIS_URL was dropped, and beside a URL with no path the db came out None.
    """

    def test_url_path_applies_when_no_db_is_set(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/2")
        assert _kwargs(create_redis_client())["db"] == 2

    def test_an_explicit_db_beats_the_url_path(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/2")
        monkeypatch.setenv("REDIS_DB", "3")
        assert _kwargs(create_redis_client())["db"] == 3

    def test_an_explicit_db_applies_to_a_pathless_url(self, monkeypatch):
        """This used to yield db=None — neither the env nor a sane default."""
        monkeypatch.setenv("REDIS_URL", "redis://h:6379")
        monkeypatch.setenv("REDIS_DB", "3")
        assert _kwargs(create_redis_client())["db"] == 3

    def test_a_prefix_db_survives_an_inherited_url(self, monkeypatch):
        """The chart's shape: one REDIS_URL, CACHE_REDIS_DB=1 beside it."""
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
        monkeypatch.setenv("CACHE_REDIS_DB", "1")
        assert _kwargs(create_redis_client(env_prefix="CACHE_REDIS_"))["db"] == 1

    def test_an_explicit_argument_still_wins(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/2")
        monkeypatch.setenv("REDIS_DB", "3")
        assert _kwargs(create_redis_client(db=7))["db"] == 7


class TestContainerAllowlists:
    """The two hand-maintained env allowlists must carry what this module READS,
    AND must actually copy it into the container.

    Tool containers and sidecars get a hand-picked environment, not an inherited
    one, so a variable missing from a list applies everywhere EXCEPT the processes
    doing the work — silently, because the default is a working value. Both
    omissions found in review (REDIS_HEALTH_CHECK_INTERVAL from both lists) were
    of exactly this shape, and nothing kept the two lists in step.

    TWO mechanisms, both checked. Declaring the name on Env / ToolRuntimeVariable
    does nothing on its own: a separate loop copies a fixed tuple of those
    constants into the child environment, and a name can be declared and left out
    of the tuple. The first version of this class asserted only the declaration,
    so deleting `Env.REDIS_HEALTH_CHECK_INTERVAL` from runner.py's tuple — the
    exact omission the class was written for — left the suite green.

    _SHARED is DERIVED from redis_client.py's source rather than hand-listed, so a
    variable added to the module fails this guard instead of needing a third list
    to be remembered. REDIS_SSL_CHECK_HOSTNAME was added by the same commit that
    introduced the hand-written version and was missing from it.

    Read as text rather than imported: neither package is installable in this
    environment, and the question is what the source declares and forwards.
    """

    _ROOT = pathlib.Path(__file__).resolve().parents[3]
    _SIDECAR = _ROOT / "runner/src/unstract/runner/constants.py"
    _SIDECAR_FORWARD = _ROOT / "runner/src/unstract/runner/runner.py"
    _TOOL = (
        _ROOT / "unstract/workflow-execution/src/unstract/workflow_execution/constants.py"
    )
    _TOOL_FORWARD = (
        _ROOT
        / "unstract/workflow-execution/src/unstract/workflow_execution/tools_utils.py"
    )
    _CLIENT = _ROOT / "unstract/core/src/unstract/core/cache/redis_client.py"

    # Variables that are per-PROCESS rather than per-endpoint, so a container
    # deliberately does not inherit them. Listing them here (with the reason) is
    # what keeps the derivation below honest: anything else new must be forwarded
    # or explicitly excused.
    _NOT_FORWARDED = {
        # Sentinel is the self-hosted HA path; a sidecar or tool container is
        # handed the resolved endpoint, it does not do discovery itself.
        "REDIS_SENTINEL_MODE",
        "REDIS_SENTINEL_MASTER_NAME",
        # Host/port/credentials were already forwarded before UN-4123 under their
        # own names; they are not part of this TLS-era set.
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_USER",
        "REDIS_USERNAME",
        "REDIS_PASSWORD",
    }

    @classmethod
    def _shared(cls) -> set[str]:
        """Every REDIS_* env var redis_client.py reads, minus the excused ones."""
        source = cls._CLIENT.read_text()
        # Scans the ARGUMENTS of every env-reading call, not just os.getenv.
        # Keying on os.getenv alone meant that rewriting a read to go through
        # env_chain made the variable invisible here — the TLS set dropped out
        # of this guard silently, which is the same drift this class exists to
        # catch. Scoped to these call names rather than the whole file so a
        # variable merely NAMED in a docstring is not demanded of every
        # container.
        calls = re.findall(
            r"(?:os\.getenv|env_chain|env_chain_named)\("
            r"([^()]*(?:\([^()]*\)[^()]*)*)\)",
            source,
        )
        names: set[str] = set()
        for args in calls:
            names |= set(re.findall(r'"(REDIS_[A-Z_]+)"', args))
            names |= {
                f"REDIS_{suffix}"
                for suffix in re.findall(r'f"\{env_prefix\}([A-Z_]+)"', args)
            }
        return names - cls._NOT_FORWARDED

    def test_the_derived_set_is_not_empty(self):
        """A regex that silently matches nothing would make every case below pass."""
        shared = self._shared()
        assert len(shared) >= 6, shared
        assert "REDIS_SSL_CHECK_HOSTNAME" in shared

    @pytest.mark.parametrize("which", ["sidecar", "tool"])
    def test_every_variable_this_module_reads_is_declared(self, which):
        path = self._SIDECAR if which == "sidecar" else self._TOOL
        declared = path.read_text()
        missing = [name for name in sorted(self._shared()) if f'"{name}"' not in declared]
        assert not missing, (
            f"{path.name} does not declare {missing}; create_redis_client reads "
            "them, so the setting would apply everywhere except this container."
        )

    # The exact region of each file that copies constants into the child
    # environment. Searching the WHOLE file instead would accept any occurrence —
    # a comment, a docstring, a different tuple — which is the same
    # "present somewhere != present where it matters" weakness this class was
    # rewritten to remove, one level down. Mutation-proved: with a whole-file
    # search, COMMENTING OUT a tuple entry survived.
    _FORWARD_REGIONS = {
        "sidecar": ("for _redis_env in (", ")"),
        "tool": ("for name in (", ")"),
    }

    @classmethod
    def _forwarding_tuple(cls, which: str) -> str:
        """The tuple's LIVE lines — commented-out entries do not forward anything."""
        path = cls._SIDECAR_FORWARD if which == "sidecar" else cls._TOOL_FORWARD
        source = path.read_text()
        opener, closer = cls._FORWARD_REGIONS[which]
        start = source.index(opener)
        region = source[start : source.index(closer, start)]
        return "\n".join(
            line for line in region.splitlines() if not line.strip().startswith("#")
        )

    @pytest.mark.parametrize("which", ["sidecar", "tool"])
    def test_the_forwarding_tuple_is_locatable(self, which):
        """If the anchor stops matching, every case below would search an empty
        string and fail loudly — but say so here, where the cause is obvious.
        """
        region = self._forwarding_tuple(which)
        assert "REDIS_" in region, region

    @pytest.mark.parametrize("which", ["sidecar", "tool"])
    def test_every_declared_variable_is_actually_copied_into_the_container(self, which):
        """The tuple, not the constants file, is what reaches the child process."""
        alias = "Env." if which == "sidecar" else "ToolRV."
        region = self._forwarding_tuple(which)
        missing = [
            name for name in sorted(self._shared()) if f"{alias}{name}," not in region
        ]
        assert not missing, (
            f"{which} declares but never forwards {missing}: the constant exists "
            "and the loop that copies it into the container skips it (or has it "
            "commented out), so the variable silently stops at the parent process."
        )

    def test_the_tool_list_also_carries_the_sdk1_metrics_database(self):
        """sdk1 runs in tool containers; the sidecar never imports it."""
        assert '"METRICS_REDIS_DB"' in self._TOOL.read_text()
        assert '"METRICS_REDIS_DB"' not in self._SIDECAR.read_text()


class TestCertReqsNoneInTheUrl:
    """A URL carrying ?ssl_cert_reqs=none must not also get ssl_check_hostname.

    Python's ssl module raises `Cannot set verify_mode to CERT_NONE when
    check_hostname is enabled`, so the pair is not a degraded connection — it is
    NO connection, on every client in the process, at the first command rather
    than at startup. The suppression used to test the ENV value only, so a URL
    saying `none` with the env at its "required" default got check_hostname
    bolted on. docker/redis-tls/README.md documents that exact URL.

    The older test for this input asserted only that ssl_cert_reqs=none was
    PRESENT, which the broken output also satisfied.
    """

    _URL = "rediss://h:6380/0?ssl_cert_reqs=none"

    def _assert_compatible(self, cert_reqs, check_hostname):
        """The combination the ssl module actually refuses."""
        assert not (check_hostname and cert_reqs == "none"), (
            f"ssl_cert_reqs={cert_reqs!r} with ssl_check_hostname={check_hostname!r} "
            "raises ValueError at handshake setup"
        )

    def test_the_client_kwargs_are_not_contradictory(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", self._URL)
        kwargs = _kwargs(create_redis_client())
        self._assert_compatible(
            kwargs.get("ssl_cert_reqs"), kwargs.get("ssl_check_hostname")
        )

    def test_the_client_builds_a_usable_ssl_context(self, monkeypatch):
        """End to end: what redis-py does with those kwargs at connect time."""
        import ssl as _ssl

        monkeypatch.setenv("REDIS_URL", self._URL)
        conn = create_redis_client().connection_pool.make_connection()
        context = _ssl.create_default_context()
        # redis-py's SSLConnection._wrap_socket_with_ssl, in the order it does it.
        context.check_hostname = conn.check_hostname
        context.verify_mode = conn.cert_reqs

    def test_the_socketio_url_gains_no_check_hostname(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", self._URL)
        url = build_socketio_redis_url()
        assert "ssl_check_hostname" not in url, url
        assert url.count("ssl_cert_reqs") == 1

    def test_an_optional_cert_reqs_in_the_url_still_gets_hostname_checking(
        self, monkeypatch
    ):
        """Only `none` suppresses it — the guard must not be a blanket opt-out."""
        monkeypatch.setenv("REDIS_URL", "rediss://h:6380/0?ssl_cert_reqs=optional")
        assert "ssl_check_hostname=true" in build_socketio_redis_url()


class TestBlankAndMalformedTlsValues:
    """Blank means UNSET, and a value that is neither blank nor valid says so.

    `os.getenv` reports "" as SET, so a bare `== "true"` read the repo's own
    "leave the default" spelling as False — turning hostname verification OFF
    while the operator believed they were on the new secure default.
    """

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_check_hostname_keeps_the_secure_default(
        self, monkeypatch, raw, caplog
    ):
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CHECK_HOSTNAME", raw)
        assert _resolve_redis_env("REDIS_")["ssl_check_hostname"] is True
        # Blank is the CONVENTION, not a malformed value. Without this the test
        # cannot tell "unset" from "unparseable, warned, fell back" — both give
        # True, but only one of them is silent.
        assert "REDIS_SSL_CHECK_HOSTNAME" not in caplog.text

    @pytest.mark.parametrize("raw", ["1", "yes", "TRUE", "On"])
    def test_other_truthy_spellings_are_accepted(self, monkeypatch, raw):
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CHECK_HOSTNAME", raw)
        assert _resolve_redis_env("REDIS_")["ssl_check_hostname"] is True

    @pytest.mark.parametrize("raw", ["0", "no", "FALSE", "Off"])
    def test_other_falsy_spellings_are_accepted(self, monkeypatch, raw):
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CHECK_HOSTNAME", raw)
        assert _resolve_redis_env("REDIS_")["ssl_check_hostname"] is False

    def test_an_unknown_check_hostname_warns_and_stays_secure(self, monkeypatch, caplog):
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CHECK_HOSTNAME", "maybe")
        assert _resolve_redis_env("REDIS_")["ssl_check_hostname"] is True
        assert "REDIS_SSL_CHECK_HOSTNAME" in caplog.text

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_cert_reqs_falls_back_to_required(self, monkeypatch, raw, caplog):
        """Blank used to resolve THREE ways: RedisError on the discrete client,
        a silent CERT_NONE on the kombu URL, and "required" on the URL path.
        """
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CERT_REQS", raw)
        assert _resolve_redis_env("REDIS_")["ssl_cert_reqs"] == "required"
        assert "ssl_cert_reqs=required" in build_socketio_redis_url()
        assert "REDIS_SSL_CERT_REQS" not in caplog.text

    @pytest.mark.parametrize("raw", ["None", "none ", "REQUIRED"])
    def test_cert_reqs_is_normalised(self, monkeypatch, raw):
        """The "is verification off?" test is an equality check, so case and
        whitespace decided whether ssl_check_hostname was suppressed.
        """
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CERT_REQS", raw)
        assert _resolve_redis_env("REDIS_")["ssl_cert_reqs"] == raw.strip().lower()

    def test_an_invalid_cert_reqs_warns_and_falls_back(self, monkeypatch, caplog):
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CERT_REQS", "strict")
        assert _resolve_redis_env("REDIS_")["ssl_cert_reqs"] == "required"
        assert "REDIS_SSL_CERT_REQS" in caplog.text

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_a_blank_db_does_not_raise(self, monkeypatch, raw, caplog):
        """int("") used to escape create_redis_client as a bare ValueError that
        named neither the variable nor the prefix.
        """
        monkeypatch.setenv("REDIS_DB", raw)
        assert _kwargs(create_redis_client())["db"] == 0
        assert "REDIS_DB" not in caplog.text

    def test_an_unparseable_db_warns_rather_than_raising(self, monkeypatch, caplog):
        monkeypatch.setenv("REDIS_DB", "two")
        assert _kwargs(create_redis_client())["db"] == 0
        assert "REDIS_DB" in caplog.text

    def test_a_plaintext_url_beside_ssl_true_is_announced(self, monkeypatch, caplog):
        """The operator believes TLS is on; the wire is cleartext."""
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
        _resolve_redis_env("REDIS_")
        assert "will NOT be encrypted" in caplog.text


class TestSentinelHostnameVerification:
    """Sentinel masters are reached by the IP `get-master-addr-by-name` returns.

    SentinelManagedConnection.connect_to assigns that address to self.host, and
    SSLConnection passes self.host as server_hostname — so hostname verification
    on a master connection is checked against an IP that no DNS SAN covers, and
    an IP SAN is not a workable answer because the address changes on failover.
    Defaulting it on would have broken every existing REDIS_SENTINEL_MODE +
    REDIS_SSL deployment on upgrade, through the full ten-attempt backoff.

    The DISCOVERY connections do use the configured service name, so they keep
    verification on.
    """

    def _planes(self, prefix="REDIS_"):
        env = _resolve_redis_env(prefix, default_port="26379")
        discovery = _build_connection_kwargs(env, True, 5, 5, include_auth_only=True)
        master = _build_connection_kwargs(env, True, 5, 5, sentinel_master=True)
        return discovery, master

    def test_the_master_plane_does_not_verify_the_hostname_by_default(self, monkeypatch):
        monkeypatch.setenv("REDIS_SENTINEL_MODE", "true")
        monkeypatch.setenv("REDIS_SSL", "true")
        discovery, master = self._planes()
        assert discovery["ssl_check_hostname"] is True
        assert master["ssl_check_hostname"] is False

    def test_an_explicit_request_is_honoured_on_both_planes(self, monkeypatch):
        """The default is a compatibility choice, not a ceiling."""
        monkeypatch.setenv("REDIS_SENTINEL_MODE", "true")
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CHECK_HOSTNAME", "true")
        discovery, master = self._planes()
        assert discovery["ssl_check_hostname"] is True
        assert master["ssl_check_hostname"] is True

    def test_an_explicit_false_still_turns_discovery_off(self, monkeypatch):
        monkeypatch.setenv("REDIS_SENTINEL_MODE", "true")
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CHECK_HOSTNAME", "false")
        discovery, master = self._planes()
        assert discovery["ssl_check_hostname"] is False
        assert master["ssl_check_hostname"] is False

    def test_a_typo_does_not_count_as_an_explicit_request(self, monkeypatch):
        """Otherwise a typo re-breaks the Sentinel masters this default protects."""
        monkeypatch.setenv("REDIS_SENTINEL_MODE", "true")
        monkeypatch.setenv("REDIS_SSL", "true")
        monkeypatch.setenv("REDIS_SSL_CHECK_HOSTNAME", "ture")
        _, master = self._planes()
        assert master["ssl_check_hostname"] is False

    def test_the_standalone_path_is_unaffected(self, monkeypatch):
        monkeypatch.setenv("REDIS_SSL", "true")
        assert _kwargs(create_redis_client())["ssl_check_hostname"] is True


class TestGenericDbDoesNotCrossIntoAPrefixUrl:
    """A prefix that brought its OWN url owns its own database.

    workers/sample.env ships REDIS_DB=0 uncommented, so reading the generic var
    as a fallback meant CACHE_REDIS_URL=rediss://…/1 silently landed on db 0 —
    an unrelated global overriding the path the operator wrote, which is not the
    rule the docstring, sample.env or the chart state. An INHERITED generic URL
    still honours the prefix's db: that is the chart's shape (one REDIS_URL,
    CACHE_REDIS_DB=1) and the reason the rule exists at all.
    """

    def test_a_prefix_url_keeps_its_path_against_the_generic_db(self, monkeypatch):
        monkeypatch.setenv("REDIS_DB", "0")
        monkeypatch.setenv("CACHE_REDIS_URL", "redis://h:6380/1")
        assert _kwargs(create_redis_client("CACHE_REDIS_"))["db"] == 1

    def test_the_prefixs_own_db_still_wins(self, monkeypatch):
        monkeypatch.setenv("REDIS_DB", "0")
        monkeypatch.setenv("CACHE_REDIS_URL", "redis://h:6380/1")
        monkeypatch.setenv("CACHE_REDIS_DB", "2")
        assert _kwargs(create_redis_client("CACHE_REDIS_"))["db"] == 2

    def test_an_inherited_url_still_honours_the_prefix_db(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
        monkeypatch.setenv("CACHE_REDIS_DB", "1")
        assert _kwargs(create_redis_client("CACHE_REDIS_"))["db"] == 1

    def test_an_inherited_url_still_honours_the_generic_db(self, monkeypatch):
        """A prefix with NEITHER its own URL nor its own DB inherits both generics.

        (The REDIS_-prefix case — where the two levels are literally the same
        variable — is covered by TestDatabaseRule.)
        """
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
        monkeypatch.setenv("REDIS_DB", "3")
        assert _kwargs(create_redis_client("CACHE_REDIS_"))["db"] == 3


class TestUrlCertReqsParsing:
    """`url_cert_reqs` is what decides whether hostname checking is suppressed.

    Each of these survived the suite before it was pinned.
    """

    def test_it_takes_the_first_value_on_a_repeat(self, monkeypatch):
        """Matching redis-py's parse_url, which does `unquote(value[0])`.

        Taking the last instead would disagree with the connection the URL
        actually builds — the suppression decision and the wire would differ.
        """
        monkeypatch.setenv(
            "REDIS_URL", "rediss://h:6380/0?ssl_cert_reqs=none&ssl_cert_reqs=required"
        )
        assert _resolve_redis_env("REDIS_")["ssl_check_hostname"] is False

    @pytest.mark.parametrize("raw", ["NONE", "None", "%20none%20"])
    def test_it_normalises_case_and_whitespace(self, monkeypatch, raw):
        monkeypatch.setenv("REDIS_URL", f"rediss://h:6380/0?ssl_cert_reqs={raw}")
        assert _resolve_redis_env("REDIS_")["ssl_check_hostname"] is False

    def test_a_url_without_cert_reqs_leaves_the_env_in_charge(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "rediss://h:6380/0")
        monkeypatch.setenv("REDIS_SSL_CERT_REQS", "none")
        assert _resolve_redis_env("REDIS_")["ssl_check_hostname"] is False


class TestDiscreteModeStillInheritsTheGenericDb:
    """No URL anywhere: a prefixed client falls back to REDIS_DB as it always did.

    The "at the URL's own level" rule narrows the fallback for a prefix that
    brought its OWN url. It must not narrow the plain discrete path, where there
    is no URL to own anything — that would silently move every prefixed client
    onto db 0.
    """

    def test_a_prefix_without_its_own_db_uses_the_generic_one(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_DB", "3")
        assert _kwargs(create_redis_client("CACHE_REDIS_"))["db"] == 3

    def test_the_prefixs_own_db_still_wins(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_DB", "3")
        monkeypatch.setenv("CACHE_REDIS_DB", "1")
        assert _kwargs(create_redis_client("CACHE_REDIS_"))["db"] == 1


class TestUrlModeCredentials:
    """A URL written without credentials must not connect anonymously.

    Keeping the password OUT of the URL is the safer configuration — a URL is
    printed into error messages, ArgoCD conditions and ExternalSecret templates,
    and a password in it travels to all three. That configuration is only usable
    if the separately-supplied credential is actually applied.
    """

    def test_the_configured_password_fills_a_gap_the_url_leaves(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "rediss://h:6380/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        assert _kwargs(create_redis_client())["password"] == "s3cret"

    def test_a_url_carrying_credentials_still_wins(self, monkeypatch):
        """ConnectionPool.from_url ends with kwargs.update(url_options)."""
        monkeypatch.setenv("REDIS_URL", "rediss://:in-url@h:6380/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        assert _kwargs(create_redis_client())["password"] == "in-url"

    def test_a_username_password_pair_in_the_url_wins_too(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "rediss://u:pw@h:6380/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        monkeypatch.setenv("REDIS_USER", "alice")
        kwargs = _kwargs(create_redis_client())
        assert kwargs["password"] == "pw"
        assert kwargs["username"] == "u"

    def test_the_username_rides_with_the_password(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "rediss://h:6380/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        monkeypatch.setenv("REDIS_USER", "alice")
        assert _kwargs(create_redis_client())["username"] == "alice"

    def test_a_username_alone_is_not_a_credential(self, monkeypatch):
        """values.yaml ships REDIS_USER: default, and the in-cluster server has
        no auth. Filling in a username on its own would make redis-py send AUTH
        to it — turning a working default deployment into a failing one.
        """
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
        monkeypatch.setenv("REDIS_USER", "default")
        monkeypatch.setenv("REDIS_PASSWORD", "")
        kwargs = _kwargs(create_redis_client())
        assert kwargs.get("username") is None
        assert kwargs.get("password") is None

    def test_no_credentials_anywhere_stays_anonymous(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
        assert _kwargs(create_redis_client()).get("password") is None

    def test_the_socketio_url_gains_the_credentials_too(self, monkeypatch):
        """Kombu takes a URL and nothing else, so a separately-supplied password
        cannot reach it any other way. Without this the publisher is anonymous
        against an authenticated server and Socket.IO events simply stop.
        """
        monkeypatch.setenv("REDIS_URL", "rediss://h:6380/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        # Assert on PARSED fields, not a substring: a substring check passes on
        # `rediss://alice:s3cret@alice@h:6380/0`, where the password actually
        # parses as "s3cret@alice".
        parts = urlsplit(build_socketio_redis_url())
        assert parts.password == "s3cret"
        assert parts.hostname == "h"

    def test_the_socketio_url_leaves_existing_credentials_alone(self, monkeypatch):
        """Parsed fields, not substrings — the same rule as the test above.

        `"in-url" in url` also passes on `rediss://:in-url@in-url@h:6380/0`,
        where the password parses as "in-url@in-url", and on
        `rediss://h:6380/0?note=in-url`, where there is no password at all.
        """
        monkeypatch.setenv("REDIS_URL", "rediss://:in-url@h:6380/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        parts = urlsplit(build_socketio_redis_url())
        assert parts.password == "in-url"
        assert parts.hostname == "h"

    def test_an_empty_password_in_the_url_is_treated_as_absent(self, monkeypatch):
        """`redis://:@host` parses to password "", which redis-py's own
        parse_url reads as absent (`if url.password:`). Testing `is None` would
        decline to fill a gap the library agrees is a gap — and the shape is
        what Helm produces from `redis://:{{ .Values.password }}@host` when the
        value is empty.
        """
        monkeypatch.setenv("REDIS_URL", "redis://:@h:6379/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        assert _kwargs(create_redis_client())["password"] == "s3cret"

    def test_a_username_only_url_still_gets_the_password(self, monkeypatch):
        """`redis://alice@host` carries an @ but NO password.

        Treating the @ as evidence of credentials dropped the separately
        supplied password and left the client unable to authenticate.
        """
        monkeypatch.setenv("REDIS_URL", "redis://alice@h:6379/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        kwargs = _kwargs(create_redis_client())
        assert kwargs["password"] == "s3cret"
        assert kwargs["username"] == "alice"


class TestUrlCredentialsAreResolvedAtTheUrlsLevel:
    """Same rule as the database: a prefix that brought its OWN url owns its
    own credentials.

    That url may point at a DIFFERENT endpoint, and an anonymous one; letting
    the generic REDIS_PASSWORD reach across would make the client send AUTH to
    a server that has none, breaking a connection that worked before.
    """

    def test_a_prefix_url_does_not_inherit_the_generic_password(self, monkeypatch):
        monkeypatch.setenv("CACHE_REDIS_URL", "redis://anon:6379/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        assert _kwargs(create_redis_client("CACHE_REDIS_")).get("password") is None

    def test_the_prefixs_own_password_applies(self, monkeypatch):
        monkeypatch.setenv("CACHE_REDIS_URL", "redis://anon:6379/0")
        monkeypatch.setenv("CACHE_REDIS_PASSWORD", "own")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        assert _kwargs(create_redis_client("CACHE_REDIS_"))["password"] == "own"

    def test_an_inherited_url_still_uses_the_generic_password(self, monkeypatch):
        """Same endpoint as the generic one, so the fallback chain applies."""
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        assert _kwargs(create_redis_client("CACHE_REDIS_"))["password"] == "s3cret"

    def test_the_socketio_url_follows_the_same_rule(self, monkeypatch):
        monkeypatch.setenv("CACHE_REDIS_URL", "rediss://anon:6379/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        # A bare `"s3cret" not in url` also passes on "" and on any mangled
        # output, so the endpoint is pinned too.
        parts = urlsplit(build_socketio_redis_url("CACHE_REDIS_"))
        assert parts.password is None
        assert parts.hostname == "anon"


class TestSocketIoUrlCredentials:
    """The Socket.IO builder must agree with create_redis_client on every shape.

    Its output is a STRING handed to kombu, so a malformed one authenticates
    with a wrong secret rather than none — and `socketio.Server` is constructed
    with logger=False, so the symptom is events silently stopping.
    """

    def test_a_username_only_url_keeps_its_host_and_gets_the_password(self, monkeypatch):
        """`parts.netloc` INCLUDES userinfo; prepending to it produced
        `alice:pw@alice@host`, and userinfo splits on the LAST @.
        """
        monkeypatch.setenv("REDIS_URL", "redis://alice@h:6379/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        parts = urlsplit(build_socketio_redis_url())
        assert parts.hostname == "h"
        assert parts.username == "alice"
        assert parts.password == "s3cret"

    def test_an_encoded_username_is_not_double_encoded(self, monkeypatch):
        """It is percent-encoded already; quoting it again gave `al%2540ice`."""
        monkeypatch.setenv("REDIS_URL", "redis://al%40ice@h:6379/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        # Asserted POSITIVELY: `"%2540" not in url` is equally satisfied by a
        # URL that dropped the username, or replaced it with REDIS_USER.
        assert urlsplit(build_socketio_redis_url()).username == "al%40ice"

    def test_a_password_with_url_metacharacters_is_encoded(self, monkeypatch):
        """Unencoded, `p@ss/w:rd` reparses with host "ss" — a DIFFERENT server."""
        monkeypatch.setenv("REDIS_URL", "rediss://h:6380/0")
        monkeypatch.setenv("REDIS_PASSWORD", "p@ss/w:rd")
        url = build_socketio_redis_url()
        assert urlsplit(url).hostname == "h"
        # Round-trip, not a spelling check. The hostname guard catches the
        # host half of a doubled userinfo but not the credential half:
        # `rediss://x:p%40ss%2Fw%3Ard@p%40ss%2Fw%3Ard@h:6380/0` has hostname
        # "h" and contains the substring, yet kombu would send
        # "p@ss/w:rd@p@ss/w:rd". unquote() is what kombu itself applies.
        assert unquote(urlsplit(url).password) == "p@ss/w:rd"

    def test_an_empty_password_in_the_url_is_treated_as_absent(self, monkeypatch):
        """`redis://:@host` parses to "", which redis-py and kombu both read as
        no password — so the separately supplied one must fill the gap.
        """
        monkeypatch.setenv("REDIS_URL", "redis://:@h:6379/0")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        assert urlsplit(build_socketio_redis_url()).password == "s3cret"

    def test_a_username_alone_stays_anonymous(self, monkeypatch):
        """values.yaml ships REDIS_USER: default against an unauthenticated
        in-cluster server; adding credentials here would break it.
        """
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
        monkeypatch.setenv("REDIS_USER", "default")
        monkeypatch.setenv("REDIS_PASSWORD", "")
        assert build_socketio_redis_url() == "redis://h:6379/0"

    def test_the_prefix_username_spelling_is_honoured(self, monkeypatch):
        """{prefix}USERNAME is the compatibility spelling of {prefix}USER."""
        monkeypatch.setenv("CACHE_REDIS_URL", "redis://h:6379/0")
        monkeypatch.setenv("CACHE_REDIS_PASSWORD", "pw")
        monkeypatch.setenv("CACHE_REDIS_USERNAME", "alice")
        assert urlsplit(build_socketio_redis_url("CACHE_REDIS_")).username == "alice"


class TestTheConsumersAgreeOnTheUsername:
    """The client, the Socket.IO URL and the Django cache must resolve the SAME
    ACL user. Each was previously pinned only to itself, so a change that made
    them disagree passed every test.
    """

    def test_a_url_username_outranks_the_configured_one(self, monkeypatch):
        """Both set at once is the only environment that tells the two apart.

        values.yaml ships REDIS_USER: default, so pairing it with a URL that
        names a different user is an ordinary config — and reversing the
        precedence made the client authenticate as `alice` while kombu and the
        Django cache authenticated as `default`. On an endpoint where `default`
        is disabled, Socket.IO events stop and nothing else does.
        """
        monkeypatch.setenv("REDIS_URL", "redis://alice@h:6379/0")
        monkeypatch.setenv("REDIS_PASSWORD", "pw")
        monkeypatch.setenv("REDIS_USER", "default")
        assert urlsplit(build_socketio_redis_url()).username == "alice"
        assert _kwargs(create_redis_client())["username"] == "alice"

    def test_a_password_only_url_takes_no_username_from_the_env(self, monkeypatch):
        """The `not parts.password` guard is load-bearing for the USERNAME.

        For the password it is not: from_url ends with kwargs.update(url_options)
        so the URL's password wins either way. Dropping the guard therefore
        looks harmless and is not — it lets REDIS_USER ride along, turning a
        one-argument `AUTH <pw>` into a two-argument `AUTH alice <pw>` while the
        Socket.IO URL for the same config still sends the one-argument form.
        """
        monkeypatch.setenv("REDIS_URL", "redis://:urlpw@h:6379/0")
        monkeypatch.setenv("REDIS_PASSWORD", "envpw")
        monkeypatch.setenv("REDIS_USER", "alice")
        kwargs = _kwargs(create_redis_client())
        assert kwargs["password"] == "urlpw"
        assert kwargs.get("username") is None
        assert urlsplit(build_socketio_redis_url()).username in (None, "")

    def test_the_username_env_var_has_two_spellings(self, monkeypatch):
        """REDIS_USER is what the chart writes; REDIS_USERNAME is what
        platform-service/sample.env writes. One shared credential secret can
        inject either, so a consumer that reads only one authenticates as a
        different user than the client beside it.
        """
        monkeypatch.delenv("REDIS_USER", raising=False)
        monkeypatch.setenv("REDIS_USERNAME", "alice")
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
        monkeypatch.setenv("REDIS_PASSWORD", "pw")
        assert urlsplit(build_socketio_redis_url()).username == "alice"
        assert _kwargs(create_redis_client())["username"] == "alice"

    def test_a_blank_user_falls_through_to_the_other_spelling(self, monkeypatch):
        """`REDIS_USER=` is the "leave it unset" spelling the recipes use, and
        `os.getenv(name, fallback)` would hand back the blank instead."""
        monkeypatch.setenv("REDIS_USER", "")
        monkeypatch.setenv("REDIS_USERNAME", "alice")
        monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
        monkeypatch.setenv("REDIS_PASSWORD", "pw")
        assert urlsplit(build_socketio_redis_url()).username == "alice"


class TestBlankMeansUnsetForTlsToo:
    """The convention has to cover TLS, not just credentials.

    Once a blank prefixed PASSWORD fell through to the generic one but a blank
    prefixed SSL did not, `CACHE_REDIS_SSL=` beside `REDIS_SSL=true` gave the
    worker cache a real AUTH over an UNENCRYPTED socket — the credential the
    same change taught it to inherit, now in clear on the wire.
    """

    @pytest.mark.parametrize(
        "blank,generic,key,expected",
        [
            ("CACHE_REDIS_SSL", ("REDIS_SSL", "true"), "ssl", True),
            (
                "CACHE_REDIS_SSL_CERT_REQS",
                ("REDIS_SSL_CERT_REQS", "none"),
                "ssl_cert_reqs",
                "none",
            ),
            (
                "CACHE_REDIS_SSL_CHECK_HOSTNAME",
                ("REDIS_SSL_CHECK_HOSTNAME", "false"),
                "ssl_check_hostname",
                False,
            ),
            (
                "CACHE_REDIS_SSL_CA_CERTS",
                ("REDIS_SSL_CA_CERTS", "/etc/ca.pem"),
                "ssl_ca_certs",
                "/etc/ca.pem",
            ),
        ],
    )
    def test_a_blank_prefixed_tls_var_does_not_shadow(
        self, monkeypatch, blank, generic, key, expected
    ):
        monkeypatch.setenv(generic[0], generic[1])
        monkeypatch.setenv(blank, "")
        assert _resolve_redis_env("CACHE_REDIS_")[key] == expected


class TestEnvChainHelpers:
    """The helpers the consumers share. Each had a one-line failure mode."""

    def test_env_chain_returns_the_raw_value_not_a_stripped_one(self, monkeypatch):
        """A file-mounted secret ends in a newline. Stripping the RETURN value
        truncated it here while backend/settings/base.py read the same variable
        unstripped, so one process authenticated two different ways."""
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret\n")
        assert env_chain("REDIS_PASSWORD") == "s3cret\n"

    def test_env_chain_skips_whitespace_only_values(self, monkeypatch):
        monkeypatch.setenv("CACHE_REDIS_PASSWORD", "   ")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        assert env_chain("CACHE_REDIS_PASSWORD", "REDIS_PASSWORD") == "s3cret"

    def test_env_chain_named_reports_the_variable_that_was_set(self, monkeypatch):
        """So a warning cannot send an operator grepping for an unset key."""
        monkeypatch.delenv("CACHE_REDIS_PORT", raising=False)
        monkeypatch.setenv("REDIS_PORT", "6380")
        assert env_chain_named("CACHE_REDIS_PORT", "REDIS_PORT") == ("6380", "REDIS_PORT")

    def test_url_username_from_env_honours_the_same_blank_rule(self, monkeypatch):
        monkeypatch.setenv("REDIS_USER", "   ")
        monkeypatch.setenv("REDIS_USERNAME", "alice")
        assert url_username_from_env() == "alice"

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_parse_port_treats_blank_as_unset(self, raw, caplog):
        """Quietly, too. base.py hands this the raw env value rather than
        env_chain's None, so treating "" as unparseable logged an ERROR at
        startup in the backend and nowhere else — for the repo's own
        "leave the default" spelling."""
        with caplog.at_level(logging.ERROR):
            assert parse_port(raw, "REDIS_PORT", 6379) == 6379
        assert caplog.text == ""

    def test_parse_port_falls_back_on_an_unparseable_value(self, caplog):
        with caplog.at_level(logging.ERROR):
            assert parse_port("638O", "REDIS_PORT", 6379) == 6379
        assert "REDIS_PORT" in caplog.text

    def test_parse_port_returns_an_int(self):
        assert parse_port("6380", "REDIS_PORT", 6379) == 6380
