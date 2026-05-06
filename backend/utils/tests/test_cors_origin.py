"""Regression tests for utils.cors_origin — the CORS origin matcher and
URL normalizer that gate browser ``Origin`` headers on every Django request
and SocketIO handshake.

UN-3439: production socket connections silently failed for wildcard subdomains
because python-socketio does exact-string comparison. These tests pin the
contract so the next refactor can't reopen the hole.
"""

from __future__ import annotations

import time

import pytest

from utils.cors_origin import RegexOrigin, normalize_web_app_origin


class TestRegexOrigin:
    def test_subdomain_matches(self):
        ro = RegexOrigin(r"^https://[^/]+\.example\.com$")
        assert ("https://app.example.com" == ro) is True
        assert ("https://api.example.com" == ro) is True

    def test_deep_subdomain_matches(self):
        """Multi-level subdomains are accepted — DNS-owned by the same party."""
        ro = RegexOrigin(r"^https://[^/]+\.example\.com$")
        assert ("https://dev.env.example.com" == ro) is True

    def test_apex_does_not_match(self):
        """Apex is covered by the exact-match CORS_ALLOWED_ORIGINS entry, not
        the wildcard regex."""
        ro = RegexOrigin(r"^https://[^/]+\.example\.com$")
        assert ("https://example.com" == ro) is False

    def test_lookalike_rejected(self):
        ro = RegexOrigin(r"^https://[^/]+\.example\.com$")
        assert ("https://attacker-example.com" == ro) is False
        assert ("https://example.com.attacker.com" == ro) is False
        assert ("https://x.example.com.attacker.com" == ro) is False

    def test_wrong_scheme_rejected(self):
        ro = RegexOrigin(r"^https://[^/]+\.example\.com$")
        # NOSONAR — the `http://` URL is intentional test data: we are
        # asserting it is *rejected* by an https-scoped pattern.
        assert ("http://app.example.com" == ro) is False  # NOSONAR

    def test_trailing_newline_rejected(self):
        """``fullmatch`` (not ``match``) is required so ``$`` doesn't permit
        a trailing ``\\n`` per Python regex semantics."""
        ro = RegexOrigin(r"^https://[^/]+\.example\.com$")
        assert ("https://app.example.com\n" == ro) is False

    def test_in_operator_routes_to_eq(self):
        """``origin in allowed_origins`` is exactly how python-socketio gates
        the engine.io handshake — verify Python's reflected ``__eq__`` kicks in."""
        allowed = [RegexOrigin(r"^https://[^/]+\.example\.com$")]
        assert "https://app.example.com" in allowed
        assert "https://evil.com" not in allowed

    def test_non_string_returns_not_implemented(self):
        """``__eq__`` must return the ``NotImplemented`` sentinel (not
        ``False``) for non-strings so Python's reflected-equality protocol
        can fall back to identity. Tested via direct dunder calls because
        ``ro == None`` short-circuits before reaching ``__eq__``."""
        ro = RegexOrigin(r"^x$")
        assert ro.__eq__(None) is NotImplemented
        assert ro.__eq__(42) is NotImplemented
        assert ro.__eq__([]) is NotImplemented

    def test_unhashable(self):
        """``__hash__ = None`` prevents the equality/hash contract from being
        violated if anyone wraps the allow-list in a ``set``/``frozenset``."""
        ro = RegexOrigin(r"^x$")
        with pytest.raises(TypeError):
            hash(ro)
        with pytest.raises(TypeError):
            # `len({ro})` builds the set (calling __hash__) and consumes it via
            # an explicit function call — keeps ruff from collapsing the
            # statement and Sonar from flagging it as side-effect-free.
            len({ro})

    def test_no_redos(self):
        """Pattern must complete on hostile input — ``[^/]+`` has no nested
        quantifiers so backtracking is bounded. Threshold is generous (500ms)
        so noisy CI runners don't flake; ReDoS would blow up by orders of
        magnitude past this."""
        ro = RegexOrigin(r"^https://[^/]+\.example\.com$")
        hostile = "https://" + "a" * 10000 + ".evil.com"
        start = time.perf_counter()
        _ = hostile in [ro]
        assert time.perf_counter() - start < 0.5


class TestNormalizeWebAppOrigin:
    def test_basic_https(self):
        origin, wildcard, _ = normalize_web_app_origin("https://example.com")
        assert origin == "https://example.com"
        assert wildcard == "https://*.example.com"

    def test_strips_trailing_slash(self):
        origin, _, _ = normalize_web_app_origin("https://example.com/")
        assert origin == "https://example.com"

    def test_strips_path_and_query(self):
        origin, _, _ = normalize_web_app_origin("https://example.com/path?q=1")
        assert origin == "https://example.com"

    def test_lowercases_hostname(self):
        """Browsers serialize ``Origin`` with a lowercase host (RFC 6454);
        django-cors-headers does case-sensitive string compare, so the env
        value must be lowercased to match."""
        origin, _, _ = normalize_web_app_origin("https://APP.EXAMPLE.COM")
        assert origin == "https://app.example.com"

    def test_drops_default_https_port(self):
        """Browsers omit the explicit default port from ``Origin`` per
        RFC 6454 — keeping ``:443`` would silently break exact match."""
        origin, _, _ = normalize_web_app_origin("https://example.com:443")
        assert origin == "https://example.com"

    def test_drops_default_http_port(self):
        # NOSONAR — `http://` URLs are intentional test data for the port
        # normalization logic, not a runtime use of the insecure protocol.
        origin, _, _ = normalize_web_app_origin("http://example.com:80")  # NOSONAR
        assert origin == "http://example.com"  # NOSONAR

    def test_keeps_non_default_port(self):
        origin, wildcard, _ = normalize_web_app_origin("https://example.com:8443")
        assert origin == "https://example.com:8443"
        assert wildcard == "https://*.example.com:8443"

    def test_localhost_default(self):
        origin, _, _ = normalize_web_app_origin("http://localhost:3000")
        assert origin == "http://localhost:3000"

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "not-a-url",
            "example.com",          # missing scheme
            "//example.com",        # protocol-relative
            "https://",             # missing host
            "ftp://example.com",  # non-browser scheme  # NOSONAR — test input asserting ftp is rejected
            "ws://example.com",  # not a top-level browser scheme
            "https://example.com:abc",  # malformed port — urlparse raises on .port access
            "https://example.com:99999",  # out-of-range port
        ],
    )
    def test_rejects_misconfigured(self, bad):
        """Fail fast at startup so misconfigured envs can't silently produce
        CORS rules that match nothing real."""
        with pytest.raises(ValueError, match="WEB_APP_ORIGIN_URL"):
            normalize_web_app_origin(bad)


class TestSubdomainRegexEndToEnd:
    """End-to-end: the regex returned by ``normalize_web_app_origin`` is what
    actually gates production. Verify via ``RegexOrigin`` (same path as
    SocketIO uses)."""

    def test_apex_env_accepts_subdomains(self):
        _, _, pattern = normalize_web_app_origin("https://us-central.unstract.com")
        ro = RegexOrigin(pattern)
        # The exact failing origins from UN-3439:
        assert "https://dev.env.us-central.unstract.com" in [ro]
        assert "https://test.env.us-central.unstract.com" in [ro]

    def test_apex_rejected_by_regex(self):
        """Apex itself is *not* matched by the wildcard regex — that's the
        exact-match CORS_ALLOWED_ORIGINS entry's job."""
        _, _, pattern = normalize_web_app_origin("https://example.com")
        ro = RegexOrigin(pattern)
        assert "https://example.com" not in [ro]

    @pytest.mark.parametrize(
        "spoof",
        [
            "https://attacker-example.com",
            "https://x.example.com.attacker.com",
            "https://example.com.attacker.com",
            "http://app.example.com",  # wrong scheme  # NOSONAR — test input asserting http is rejected
            "https://app.example.com\n",  # trailing newline
        ],
    )
    def test_spoofed_origins_rejected(self, spoof):
        _, _, pattern = normalize_web_app_origin("https://example.com")
        ro = RegexOrigin(pattern)
        assert spoof not in [ro], f"should reject {spoof!r}"

    def test_uppercase_env_still_accepts_lowercase_origin(self):
        """Browser sends lowercase even if the env was set with uppercase;
        normalization must canonicalize before regex compilation."""
        _, _, pattern = normalize_web_app_origin("https://APP.EXAMPLE.COM")
        ro = RegexOrigin(pattern)
        assert "https://sub.app.example.com" in [ro]
