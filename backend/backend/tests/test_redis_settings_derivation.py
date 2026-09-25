"""How the Redis settings block derives its URLs (UN-4123).

The block lives inside ``settings/base.py`` and runs at import, so it cannot be
called directly; these tests execute that exact source range against a controlled
environment instead of re-implementing it, which would test a copy rather than
the thing that ships.

The case that matters is REDIS_URL, because the failure it prevents is silent.
If this module built its own URL from REDIS_HOST/REDIS_PORT while
`create_redis_client` honoured REDIS_URL, the workers would follow the configured
endpoint and the backend would stay behind — and nothing would error. The API
deployment simply returns ``result: null``, because the execution's cached result
was written to one Redis and looked up in the other. That shape was found on a
live run against a managed endpoint, not by reading the code, which is why these
tests execute the shipping source rather than a copy of it.
"""

from __future__ import annotations

import logging
import pathlib
import re
from urllib.parse import urlsplit

import pytest

_SETTINGS = pathlib.Path(__file__).resolve().parents[1] / "settings" / "base.py"


def _slice_bounds(source: str) -> dict[str, tuple[int, int]]:
    """Character ranges of base.py that _derive executes.

    Factored out so the coverage guard below can assert on the SAME ranges the
    harness runs, rather than a second description of them that could drift.
    """
    defs_start = source.index('REDIS_USER = os.environ.get("REDIS_USER"')
    defs_end = (
        source.index("\n", source.index('REDIS_URL = os.environ.get("REDIS_URL"')) + 1
    )
    imports_start = source.index("from unstract.core.cache.redis_client import (")
    imports_end = source.index(")\n", imports_start) + 2
    urllib_start = source.index("from urllib.parse import ")
    urllib_end = source.index("\n", urllib_start) + 1
    return {
        "urllib": (urllib_start, urllib_end),
        "imports": (imports_start, imports_end),
        "defs": (defs_start, defs_end),
        "block": (
            source.index("REDIS_SENTINEL_MODE = ("),
            source.index("SESSION_ENGINE ="),
        ),
    }


def test_the_harness_covers_every_redis_line_in_the_settings_file():
    """The splice must not silently stop covering the code it claims to test.

    _derive executes two ranges out of base.py with a ~415-line gap between
    them, and anything in that gap is invisible to every assertion in this
    file. That is not theoretical: adding `REDIS_PASSWORD = ""` at base.py:251,
    or appending a CACHES["default"]["LOCATION"] override after SESSION_ENGINE,
    leaves all of these tests green while shipping a broken cache.

    The file already concedes the gap once — test_no_database_var_is_parsed_with
    _a_bare_int greps the source text because FILE_ACTIVE_CACHE_REDIS_DB sits
    outside both slices. A grep only covers the one pattern someone thought of;
    this covers the boundary itself, and fails naming the line that escaped.
    """
    source = _SETTINGS.read_text()
    bounds = _slice_bounds(source)
    covered = []
    for start, end in bounds.values():
        covered.append(range(start, end))

    offenders = []
    offset = 0
    for line in source.splitlines(keepends=True):
        if re.match(r"\s*(REDIS_|_redis|_cache|CACHES|SOCKET_IO)", line) and not any(
            offset in span for span in covered
        ):
            offenders.append((source[:offset].count("\n") + 1, line.strip()[:70]))
        offset += len(line)

    # Known and deliberate: these are asserted by source-text inspection
    # instead, because they are consumed far from the derivation block.
    allowed = {"FILE_ACTIVE_CACHE_REDIS_DB", "REDIS_DB_PORTAL"}
    offenders = [o for o in offenders if not any(a in o[1] for a in allowed)]

    assert not offenders, (
        "these Redis lines in base.py are OUTSIDE the ranges _derive executes, "
        "so no test in this file can observe them:\n"
        + "\n".join(f"  base.py:{n}: {text}" for n, text in offenders)
        + "\nWiden the slice, or add the name to `allowed` with a reason."
    )


def _derive(**env: str) -> dict:
    """Execute the standalone Redis block with the given env."""
    source = _SETTINGS.read_text()
    # TWO slices of the shipping file, no hand-written copies. The variable
    # DEFINITIONS (REDIS_USER … REDIS_URL) live ~400 lines above the derivation
    # block. Duplicating them in the prelude would mean the definitions never
    # execute: a mutation to any of them (a flipped REDIS_SSL default, a typo'd
    # REDIS_URI) leaves the suite green while the hand-written copy under test
    # stays correct. Both ranges therefore come from source.
    defs_start = source.index('REDIS_USER = os.environ.get("REDIS_USER"')
    defs_end = (
        source.index("\n", source.index('REDIS_URL = os.environ.get("REDIS_URL"')) + 1
    )
    start = source.index("REDIS_SENTINEL_MODE = (")
    end = source.index("SESSION_ENGINE =")

    # THREE slices, still no hand-written copies. The unstract.core import list is
    # spliced rather than retyped: a hand-written copy meant that every name the
    # settings module started importing had to be remembered here too, and the
    # symptom was fourteen NameErrors rather than one clear failure. The Socket.IO
    # URL and the TLS/db helpers are built by unstract.core so the backend and the
    # log-consumer worker cannot drift; their own cases live in
    # unstract/core/tests/test_redis_client_config.py.
    imports_start = source.index("from unstract.core.cache.redis_client import (")
    imports_end = source.index(")\n", imports_start) + 2

    # __name__ is what the relocation warning's logging.getLogger(__name__) reads;
    # without it that branch raises NameError instead of logging, which is part of
    # why it went untested.
    ns: dict = {"__name__": "backend.settings.base"}
    # The urllib import is spliced from source for the same reason as the
    # unstract.core one: a hand-written copy must be remembered every time the
    # settings module starts using another name from it, and the symptom is a
    # NameError in every case rather than one clear failure.
    urllib_start = source.index("from urllib.parse import ")
    urllib_end = source.index("\n", urllib_start) + 1

    prelude = (
        "import logging\nimport os\n"
        + source[urllib_start:urllib_end]
        + source[imports_start:imports_end]
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
        # Full string, not endswith("/3"): the failure this guards is
        # same-endpoint-WRONG-db, and endswith is equally satisfied by
        # "redis://WRONGHOST:6379/3" or a changed port.
        assert derived["CACHES"]["default"]["LOCATION"] == "redis://h:6379/3"

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
        """The silent split: a cache that ignores REDIS_URL while the workers honour it."""
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
        assert (
            "ssl_ca_certs=/etc/ssl/redis-ca.pem"
            in (derived["CACHES"]["default"]["LOCATION"])
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
        # ...and it is genuinely THERE. Asserting only the absence of the pool
        # kwargs let the whole URL-mode TLS query go untested: setting
        # check_hostname to None kept CI green while restoring redis-py's
        # unauthenticated default on the Django cache.
        location = derived["CACHES"]["default"]["LOCATION"]
        assert "ssl_cert_reqs=required" in location
        assert "ssl_check_hostname=true" in location


class TestUrlModeTlsQuery:
    """django-redis takes a LOCATION string, so URL mode's ONLY lever is the query.

    redis-py defaults ssl_check_hostname to False and overrides
    create_default_context()'s safe default with it, so a rediss:// LOCATION that
    carries neither key is encrypted but never authenticates the server.
    """

    def _location(self, **env: str) -> str:
        return _derive(**env)["CACHES"]["default"]["LOCATION"]

    def test_a_bare_tls_url_gains_both_keys(self):
        location = self._location(REDIS_URL="rediss://h:6380/0")
        assert "ssl_cert_reqs=required" in location
        assert "ssl_check_hostname=true" in location

    def test_hostname_verification_can_be_turned_off(self):
        """The documented escape hatch for a certificate with no matching SAN."""
        location = self._location(
            REDIS_URL="rediss://h:6380/0", REDIS_SSL_CHECK_HOSTNAME="false"
        )
        assert "ssl_check_hostname=false" in location

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_a_blank_escape_hatch_keeps_the_secure_default(self, raw):
        """`FOO=` is this repo's "leave the default"; a bare == "true" read it
        as False and silently dropped server authentication.
        """
        location = self._location(
            REDIS_URL="rediss://h:6380/0", REDIS_SSL_CHECK_HOSTNAME=raw
        )
        assert "ssl_check_hostname=true" in location

    def test_cert_reqs_none_in_the_url_suppresses_hostname_checking(self):
        """Python's ssl module refuses the pair — this LOCATION would make every
        cache read raise ValueError, and it is the form the TLS README documents.
        """
        location = self._location(REDIS_URL="rediss://h:6380/0?ssl_cert_reqs=none")
        assert "ssl_check_hostname" not in location

    def test_cert_reqs_none_in_the_env_suppresses_it_too(self):
        location = self._location(
            REDIS_URL="rediss://h:6380/0", REDIS_SSL_CERT_REQS="none"
        )
        assert "ssl_cert_reqs=none" in location
        assert "ssl_check_hostname" not in location

    def test_a_plaintext_url_gains_no_tls_query(self):
        assert self._location(REDIS_URL="redis://h:6379/0") == "redis://h:6379/0"


class TestTheDatabaseRuleReachesTheCache:
    """One REDIS_URL + one REDIS_DB must mean one database, backend and workers.

    django-redis ignores OPTIONS["DB"], so the LOCATION path is the only lever.
    Without it the backend followed the URL's own path while create_redis_client
    honoured REDIS_DB: workers RPUSH log_history_queue to db N, the backend LPOPs
    an empty db 0, and nothing errors.
    """

    def _location(self, **env: str) -> str:
        return _derive(**env)["CACHES"]["default"]["LOCATION"]

    def test_redis_db_rewrites_the_url_path(self):
        assert self._location(REDIS_URL="rediss://h:6380/0", REDIS_DB="2").startswith(
            "rediss://h:6380/2"
        )

    def test_the_url_path_stands_when_no_db_is_set(self):
        assert self._location(REDIS_URL="rediss://h:6380/3").startswith(
            "rediss://h:6380/3"
        )

    def test_a_pathless_url_gains_the_db(self):
        assert self._location(REDIS_URL="rediss://h:6380", REDIS_DB="4").startswith(
            "rediss://h:6380/4"
        )

    def test_the_tls_query_survives_the_rewrite(self):
        location = self._location(
            REDIS_URL="rediss://h:6380/0?ssl_ca_certs=/ca.pem", REDIS_DB="1"
        )
        assert location.startswith("rediss://h:6380/1")
        assert "ssl_ca_certs=/ca.pem" in location

    def test_it_matches_what_create_redis_client_resolves(self):
        """The two must not merely both be right today — same helper, same rule."""
        import os as _os

        from unstract.core.cache.redis_client import create_redis_client, url_db_path

        env = {"REDIS_URL": "redis://h:6379/0", "REDIS_DB": "5"}
        saved = {k: _os.environ.get(k) for k in list(_os.environ) if "REDIS" in k}
        for key in saved:
            _os.environ.pop(key, None)
        _os.environ.update(env)
        try:
            client_db = create_redis_client().connection_pool.connection_kwargs["db"]
        finally:
            for key in list(_os.environ):
                if "REDIS" in key:
                    _os.environ.pop(key, None)
            _os.environ.update({k: v for k, v in saved.items() if v is not None})
        assert url_db_path(self._location(**env)) == client_db == 5


class TestTheRelocationWarning:
    """It exists purely to be SEEN — a one-way move of a live keyspace.

    CacheService wraps get_redis_connection("default"), so log_history_queue, the
    rate-limit counters and the dashboard caches move with it, and during a
    rolling deploy old pods read the old db while new pods read the new one.
    Nothing else in the process announces that.
    """

    def test_it_fires_when_the_discrete_cache_moves_off_db_0(self, caplog):
        with caplog.at_level(logging.WARNING):
            _derive(REDIS_HOST="h", REDIS_DB="2")
        assert "moving from Redis db 0 to db 2" in caplog.text

    def test_it_fires_when_a_url_mode_cache_moves(self, caplog):
        """The mode that could newly relocate was the one that said nothing."""
        with caplog.at_level(logging.WARNING):
            _derive(REDIS_URL="redis://h:6379/1", REDIS_DB="2")
        assert "moving from Redis db 1 to db 2" in caplog.text

    def test_it_stays_quiet_when_nothing_moves(self, caplog):
        with caplog.at_level(logging.WARNING):
            _derive(REDIS_URL="redis://h:6379/3")
            _derive(REDIS_HOST="h")
        assert "moving" not in caplog.text


class TestTheBackendUsesTheSharedParsers:
    """The backend must not re-implement what unstract.core already resolves.

    Every one of these survived the suite until it was pinned, and each is a case
    where the backend and create_redis_client would give different answers for the
    same environment — the divergence class this whole change exists to remove.
    """

    def test_cert_reqs_is_normalised(self):
        """`REQUIRED` / ` none ` reached redis-py verbatim before."""
        location = _derive(REDIS_URL="rediss://h:6380/0", REDIS_SSL_CERT_REQS="NONE")[
            "CACHES"
        ]["default"]["LOCATION"]
        assert "ssl_cert_reqs=none" in location
        # ...and the normalised value must still drive the suppression, or the
        # LOCATION carries the pair ssl refuses.
        assert "ssl_check_hostname" not in location

    def test_an_invalid_cert_reqs_falls_back_rather_than_shipping_it(self):
        location = _derive(REDIS_URL="rediss://h:6380/0", REDIS_SSL_CERT_REQS="strict")[
            "CACHES"
        ]["default"]["LOCATION"]
        assert "ssl_cert_reqs=required" in location

    def test_an_unparseable_redis_db_warns_instead_of_killing_the_process(self, caplog):
        """create_redis_client warns and continues on db 0; so must this.

        `int(REDIS_DB)` here meant the workers kept running while the backend
        refused to start on the same value.
        """
        with caplog.at_level(logging.WARNING):
            derived = _derive(REDIS_HOST="h", REDIS_DB="one")
        assert derived["CACHES"]["default"]["LOCATION"] == "redis://h:6379/0"
        assert "REDIS_DB" in caplog.text

    def test_a_whitespace_only_redis_db_is_unset_and_SILENT(self, caplog):
        """This is the case that pins parse_db's own .strip().

        _resolve_redis_env strips before it calls parse_db, so through
        create_redis_client that strip is unreachable — but this module reads
        `os.environ.get("REDIS_DB", "")` raw, so it is the only caller where it
        does anything. Without it a whitespace-only value is not "unset" but
        "unparseable", and the backend warns on every boot about a variable the
        operator left blank.
        """
        with caplog.at_level(logging.WARNING):
            derived = _derive(REDIS_HOST="h", REDIS_DB="   ")
        assert derived["CACHES"]["default"]["LOCATION"] == "redis://h:6379/0"
        assert "REDIS_DB" not in caplog.text

    def test_no_database_var_is_parsed_with_a_bare_int(self):
        """Covers the sites the exec harness cannot reach.

        FILE_ACTIVE_CACHE_REDIS_DB is defined ~350 lines above the derivation
        block, outside both slices, so no _derive() case can observe it. A source
        check reaches it — and reaches the other two at the same time, which is
        the point: the defect was never one line, it was the same expression
        repeated wherever a database var is read.

        `int(os.environ.get("FILE_ACTIVE_CACHE_REDIS_DB", 0))` and
        `int(REDIS_DB)` both raise on a blank or malformed value, taking the
        process down at import — while create_redis_client, two imports away,
        warns and continues on db 0 for the very same variable.
        """
        source = _SETTINGS.read_text()
        offenders = [
            line.strip()
            for line in source.splitlines()
            if "int(" in line
            and "REDIS_DB" in line
            and "parse_db" not in line
            and not line.strip().startswith("#")
        ]
        assert not offenders, (
            f"{offenders} parse a Redis database with a bare int(); use "
            "unstract.core.cache.redis_client.parse_db so the backend and the "
            "workers agree on a malformed value."
        )


class TestUrlModeCacheCredentials:
    """The cache credentials travel in the LOCATION, through the shared helper.

    Not OPTIONS["PASSWORD"]: django-redis 5.4.0 discards OPTIONS["USERNAME"], so
    an ACL username could not reach this cache at all — it would authenticate as
    the built-in `default` user while create_redis_client in the same process
    used the configured one.

    A hand-rolled gate here also diverged from the core one within a single PR:
    it keyed on "@" being absent from the netloc, which the core comment
    explicitly rejects, leaving a username-only URL anonymous. One helper, one
    rule.
    """

    def _location(self, **env: str) -> str:
        return _derive(**env)["CACHES"]["default"]["LOCATION"]

    def test_the_password_fills_a_gap_the_url_leaves(self):
        assert (
            urlsplit(
                self._location(REDIS_URL="rediss://h:6380/0", REDIS_PASSWORD="s3cret")
            ).password
            == "s3cret"
        )

    def test_a_username_only_url_still_gets_the_password(self):
        """The shape the `@` heuristic got wrong."""
        parts = urlsplit(
            self._location(REDIS_URL="redis://alice@h:6379/0", REDIS_PASSWORD="s3cret")
        )
        assert parts.hostname == "h"
        assert parts.username == "alice"
        assert parts.password == "s3cret"

    def test_an_acl_username_reaches_the_cache(self):
        """django-redis discards OPTIONS["USERNAME"], so the LOCATION is the
        only lever. Without it the cache authenticates as `default` while the
        other consumers use the configured user.
        """
        parts = urlsplit(
            self._location(
                REDIS_URL="redis://h:6379/0", REDIS_PASSWORD="pw", REDIS_USER="alice"
            )
        )
        assert parts.username == "alice"
        assert parts.password == "pw"

    def test_a_url_carrying_credentials_is_left_alone(self):
        assert (
            urlsplit(
                self._location(
                    REDIS_URL="rediss://:in-url@h:6380/0", REDIS_PASSWORD="s3cret"
                )
            ).password
            == "in-url"
        )

    def test_no_password_stays_anonymous(self):
        assert urlsplit(self._location(REDIS_URL="rediss://h:6380/0")).password is None

    def test_the_shipped_default_user_alone_adds_nothing(self):
        """REDIS_USER defaults to "default" in this module but not in
        create_redis_client; passing the fallback would make the two send
        different AUTH forms for the same configuration.

        The password must be NON-empty. With REDIS_PASSWORD="" the helper
        returns at its `if not password` guard before the username argument is
        read at all, so the test named for this choice could not fail on it —
        mutating the call to pass the module-level REDIS_USER left the suite
        green while changing a one-argument AUTH into a two-argument one.
        """
        assert (
            self._location(REDIS_URL="redis://h:6379/0", REDIS_PASSWORD="pw")
            == "redis://:pw@h:6379/0"
        )

    def test_the_cache_honours_the_second_username_spelling(self):
        """platform-service ships REDIS_USERNAME, the chart ships REDIS_USER.

        Reading only REDIS_USER left this cache authenticating as the built-in
        `default` while create_redis_client in the SAME process authenticated
        as the configured ACL user — and where `default` is disabled, only the
        cache fails.
        """
        assert (
            self._location(
                REDIS_URL="redis://h:6379/0", REDIS_PASSWORD="pw", REDIS_USERNAME="alice"
            )
            == "redis://alice:pw@h:6379/0"
        )

    def test_discrete_mode_still_uses_options(self):
        """URL mode moved to the LOCATION; the discrete path did not change."""
        options = _derive(REDIS_HOST="h", REDIS_PASSWORD="s3cret")["CACHES"]["default"][
            "OPTIONS"
        ]
        assert options["PASSWORD"] == "s3cret"


class TestTheSslFlagParsesTheSameEverywhere:
    """REDIS_SSL decides TLS for the whole platform, so every consumer must
    read the same literals. A local `== "true"` here read `REDIS_SSL=1` as
    FALSE while unstract.core read it as True: the workers connected rediss://
    and this cache built a redis:// LOCATION and skipped its
    CONNECTION_POOL_KWARGS entirely — against a TLS-only managed endpoint the
    backend cache alone fails, and against one accepting both it authenticates
    in clear while everything else is encrypted.
    """

    @pytest.mark.parametrize("literal", ["true", "1", "yes", "on", "TRUE", " on "])
    def test_every_true_literal_switches_the_scheme(self, literal):
        derived = _derive(REDIS_HOST="h", REDIS_SSL=literal)
        assert derived["CACHES"]["default"]["LOCATION"].startswith("rediss://")
        assert derived["REDIS_SSL"] is True

    @pytest.mark.parametrize("literal", ["false", "0", "no", "off", "", "   "])
    def test_every_false_and_blank_literal_leaves_it_plaintext(self, literal):
        derived = _derive(REDIS_HOST="h", REDIS_SSL=literal)
        assert derived["CACHES"]["default"]["LOCATION"].startswith("redis://")
        assert derived["REDIS_SSL"] is False

    def test_the_pool_kwargs_follow_the_same_flag(self):
        """The scheme and the verification settings must not disagree: the
        `if REDIS_SSL` gate guards both, so a literal one reader accepts and
        the other does not strips the cert settings as well as the scheme."""
        derived = _derive(REDIS_HOST="h", REDIS_SSL="1")
        assert derived["CACHES"]["default"]["OPTIONS"]["CONNECTION_POOL_KWARGS"]
