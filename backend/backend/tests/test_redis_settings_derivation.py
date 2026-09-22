"""How the Redis settings block derives its URLs (UN-4123).

The block lives inside ``settings/base.py`` and runs at import, so it cannot be
called directly; these tests execute that exact source range against a controlled
environment instead of re-implementing it, which would test a copy rather than
the thing that ships.

The case that matters is REDIS_URL. `create_redis_client` honoured it from the
start, while this module still built its own URL from REDIS_HOST/REDIS_PORT — so
the workers moved to the configured endpoint and the backend silently stayed
behind. Nothing errors: the API deployment simply returns ``result: null``,
because the execution's cached result was written to one Redis and looked up in
the other. Found on a live run, not by reading the code.
"""

from __future__ import annotations

import pathlib

import pytest

_SETTINGS = pathlib.Path(__file__).resolve().parents[1] / "settings" / "base.py"


def _derive(**env: str) -> dict:
    """Execute the standalone Redis block with the given env."""
    source = _SETTINGS.read_text()
    # TWO slices of the shipping file, no hand-written copies. The variable
    # DEFINITIONS (REDIS_USER … REDIS_URL) live ~400 lines above the derivation
    # block, and they used to be duplicated in the prelude below — so the four
    # variables this work introduced never executed, and a mutation to any of
    # them (a flipped REDIS_SSL default, a typo'd REDIS_URI) left the suite green
    # while the copy under test stayed correct. Both ranges now come from source.
    defs_start = source.index('REDIS_USER = os.environ.get("REDIS_USER"')
    defs_end = source.index("\n", source.index('REDIS_URL = os.environ.get("REDIS_URL"')) + 1
    start = source.index("REDIS_SENTINEL_MODE = (")
    end = source.index("SESSION_ENGINE =")

    ns: dict = {}
    prelude = (
        "import logging\n"
        "import os\n"
        "from urllib.parse import quote\n"
        # The Socket.IO URL is built by unstract.core so the backend and the
        # log-consumer worker cannot drift; its own cases live in
        # unstract/core/tests/test_redis_client_config.py::TestSocketIoUrl.
        "from unstract.core.cache.redis_client import build_socketio_redis_url\n"
    ) + source[defs_start:defs_end]
    import os as _os

    saved = {k: _os.environ.get(k) for k in list(_os.environ) if "REDIS" in k}
    for key in saved:
        _os.environ.pop(key, None)
    _os.environ.update(env)
    try:
        exec(prelude + source[start:end], ns)  # noqa: S102 - the code under test
    finally:
        for key in list(_os.environ):
            if "REDIS" in key:
                _os.environ.pop(key, None)
        _os.environ.update({k: v for k, v in saved.items() if v is not None})
    return ns


@pytest.fixture
def plain() -> dict:
    return _derive(REDIS_HOST="unstract-redis", REDIS_PORT="6379")


class TestDiscreteVars:
    def test_plaintext_is_unchanged(self, plain):
        assert plain["CACHES"]["default"]["LOCATION"] == "redis://unstract-redis:6379/0"
        assert "CONNECTION_POOL_KWARGS" not in plain["CACHES"]["default"]["OPTIONS"]

    def test_the_password_reaches_the_cache(self):
        """Discrete mode is the ONLY path where the password travels in OPTIONS.

        In URL mode it rides inside the URL. Dropping this assignment left the
        whole suite green while the Django cache authenticated as nobody against
        a password-protected Redis — every read and write failing at runtime,
        nothing failing at import. This block is now built conditionally, so the
        credentials are newly reachable-or-not depending on a branch.
        """
        derived = _derive(REDIS_HOST="h", REDIS_PASSWORD="s3cret")
        assert derived["CACHES"]["default"]["OPTIONS"]["PASSWORD"] == "s3cret"

    def test_db_and_username_are_passed_through_options(self):
        """Pins the stated invariant so a django-redis bump is visible.

        The comment beside this code says USERNAME is deliberately not honoured —
        django-redis 5.4.0 discards it, so auth stays password-only as the
        built-in `default` user. That holds by accident of the pinned version:
        these assertions pin what the settings SEND, so if a bump starts reading
        USERNAME the change is a deliberate one rather than a surprise.
        """
        options = _derive(REDIS_HOST="h", REDIS_DB="3", REDIS_USER="alice")["CACHES"][
            "default"
        ]["OPTIONS"]
        assert options["DB"] == 3
        assert options["USERNAME"] == "alice"

    def test_url_mode_does_not_duplicate_credentials_into_options(self):
        """They travel in the URL; passing both risks one winning over the other."""
        options = _derive(REDIS_URL="redis://:pw@h:6379/2")["CACHES"]["default"][
            "OPTIONS"
        ]
        assert "PASSWORD" not in options
        assert "USERNAME" not in options
        assert "DB" not in options

    def test_db_travels_in_the_location(self):
        """django-redis 5.4.0 ignores OPTIONS['DB'], so the path is the only route.

        Without it this cache sits on db 0 while every other service honours
        REDIS_DB — workers RPUSH log_history_queue to db N and the backend LPOPs
        an empty db 0.
        """
        derived = _derive(REDIS_HOST="h", REDIS_DB="3")
        assert derived["CACHES"]["default"]["LOCATION"].endswith("/3")

    def test_ssl_switches_scheme_and_pool_kwargs(self):
        derived = _derive(REDIS_HOST="h", REDIS_SSL="true", REDIS_SSL_CA_CERTS="/ca.pem")
        cache = derived["CACHES"]["default"]
        assert cache["LOCATION"].startswith("rediss://")
        assert cache["OPTIONS"]["CONNECTION_POOL_KWARGS"] == {
            "ssl_cert_reqs": "required",
            "ssl_check_hostname": True,
            "ssl_ca_certs": "/ca.pem",
        }

    def test_hostname_verification_is_on_by_default(self):
        """redis-py defaults it to False and overrides ssl's safe default with it.

        A chain verified against a public CA proves nothing about WHICH server
        answered, which is the ElastiCache/Azure case this work targets.
        """
        derived = _derive(REDIS_HOST="h", REDIS_SSL="true")
        pool = derived["CACHES"]["default"]["OPTIONS"]["CONNECTION_POOL_KWARGS"]
        assert pool["ssl_check_hostname"] is True

    def test_hostname_verification_is_forced_off_when_verification_is_off(self):
        """Python's ssl raises if check_hostname is True while verify_mode is NONE."""
        derived = _derive(REDIS_HOST="h", REDIS_SSL="true", REDIS_SSL_CERT_REQS="none")
        pool = derived["CACHES"]["default"]["OPTIONS"]["CONNECTION_POOL_KWARGS"]
        assert "ssl_check_hostname" not in pool



class TestUrlMode:
    def test_url_drives_the_cache(self):
        """The regression: this used to ignore REDIS_URL entirely."""
        url = "rediss://:pw@managed.example:6380/0?ssl_cert_reqs=required"
        derived = _derive(REDIS_HOST="in-cluster", REDIS_URL=url)
        assert derived["CACHES"]["default"]["LOCATION"].startswith(url)
        assert "in-cluster" not in derived["CACHES"]["default"]["LOCATION"]

    def test_credentials_are_not_passed_twice(self):
        """In URL mode the URL is the single source for db and credentials."""
        derived = _derive(REDIS_URL="rediss://:pw@h:6380/2", REDIS_PASSWORD="other")
        options = derived["CACHES"]["default"]["OPTIONS"]
        assert "PASSWORD" not in options
        assert "DB" not in options

    def test_ca_is_appended_for_tls_urls(self):
        derived = _derive(
            REDIS_URL="rediss://h:6380/0?ssl_cert_reqs=required",
            REDIS_SSL_CA_CERTS="/etc/ssl/redis-ca.pem",
        )
        assert "ssl_ca_certs=/etc/ssl/redis-ca.pem" in (
            derived["CACHES"]["default"]["LOCATION"]
        )

    def test_ca_is_not_appended_to_a_plaintext_url(self):
        derived = _derive(
            REDIS_URL="redis://h:6379/0", REDIS_SSL_CA_CERTS="/etc/ssl/redis-ca.pem"
        )
        assert "ssl_ca_certs" not in derived["CACHES"]["default"]["LOCATION"]

    def test_an_explicit_ca_in_the_url_wins(self):
        derived = _derive(
            REDIS_URL="rediss://h:6380/0?ssl_ca_certs=/in/url.pem",
            REDIS_SSL_CA_CERTS="/env/ca.pem",
        )
        location = derived["CACHES"]["default"]["LOCATION"]
        assert location.count("ssl_ca_certs") == 1
        assert "/in/url.pem" in location


class TestSchemeFlagMismatch:
    """REDIS_SSL=true left beside an older plaintext REDIS_URL.

    The URL wins for the connection, so the flag alone must not decide the pool
    kwargs: ssl_cert_reqs reaching a plain redis.Connection is a TypeError on the
    first cache read in a request, not at startup.
    """

    def test_a_plaintext_url_does_not_get_tls_pool_kwargs(self):
        derived = _derive(REDIS_URL="redis://h:6379/0", REDIS_SSL="true")
        cache = derived["CACHES"]["default"]
        assert cache["LOCATION"] == "redis://h:6379/0"
        assert "CONNECTION_POOL_KWARGS" not in cache["OPTIONS"]

    def test_a_rediss_url_still_needs_none_of_them(self):
        """TLS travels in the URL and its query string in URL mode."""
        derived = _derive(REDIS_URL="rediss://h:6380/0", REDIS_SSL="true")
        assert "CONNECTION_POOL_KWARGS" not in derived["CACHES"]["default"]["OPTIONS"]
