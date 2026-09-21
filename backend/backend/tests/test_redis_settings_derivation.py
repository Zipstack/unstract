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
    start = source.index("REDIS_SENTINEL_MODE = (")
    end = source.index("SESSION_ENGINE =")

    ns: dict = {}
    prelude = (
        "import os\n"
        "from urllib.parse import quote\n"
        "REDIS_USER = os.environ.get('REDIS_USER', 'default')\n"
        "REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', '')\n"
        "REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')\n"
        "REDIS_PORT = os.environ.get('REDIS_PORT', '6379')\n"
        "REDIS_DB = os.environ.get('REDIS_DB', '')\n"
        "REDIS_SSL = os.environ.get('REDIS_SSL', 'false').strip().lower() == 'true'\n"
        "REDIS_SSL_CERT_REQS = os.environ.get('REDIS_SSL_CERT_REQS', 'required')\n"
        "REDIS_SSL_CA_CERTS = os.environ.get('REDIS_SSL_CA_CERTS', '').strip()\n"
        "REDIS_URL = os.environ.get('REDIS_URL', '').strip()\n"
    )
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
        assert plain["SOCKET_IO_MANAGER_URL"] == "redis://unstract-redis:6379"
        assert "CONNECTION_POOL_KWARGS" not in plain["CACHES"]["default"]["OPTIONS"]

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
            "ssl_ca_certs": "/ca.pem",
        }

    def test_socketio_pins_certificate_verification(self):
        """kombu defaults rediss:// to CERT_NONE — encrypted, but unauthenticated."""
        derived = _derive(REDIS_HOST="h", REDIS_SSL="true")
        assert "ssl_cert_reqs=required" in derived["SOCKET_IO_MANAGER_URL"]


class TestUrlMode:
    def test_url_drives_both_cache_and_socketio(self):
        """The regression: these two used to ignore REDIS_URL entirely."""
        url = "rediss://:pw@managed.example:6380/0?ssl_cert_reqs=required"
        derived = _derive(REDIS_HOST="in-cluster", REDIS_URL=url)
        assert derived["CACHES"]["default"]["LOCATION"].startswith(url)
        assert derived["SOCKET_IO_MANAGER_URL"].startswith(url)
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
