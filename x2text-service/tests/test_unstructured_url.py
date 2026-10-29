"""The unstructured-url egress guard and the timeout setting."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import pytest

from app import unstructured_url as uu

PRIVATE_URLS = [
    "http://localhost:8000/general/v0/general",
    "http://127.0.0.1:8000/x",
    "http://10.0.0.5/x",
    "http://169.254.169.254/latest/meta-data",
    "http://[::1]/x",
    "http://2130706433/x",  # 127.0.0.1 in decimal
    "http://api.localhost/x",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(uu.ALLOW_PRIVATE_ENV, raising=False)
    monkeypatch.delenv(uu.REQUEST_TIMEOUT_ENV, raising=False)


def _resolve_to(*addrs):
    return mock.patch("unstract.core.network.ssrf._resolve", return_value=set(addrs))


@pytest.mark.parametrize("value", [None, "", "true", "TRUE", "1", "yes"])
def test_private_allowed_when_unset_empty_or_true(monkeypatch, value):
    if value is not None:
        monkeypatch.setenv(uu.ALLOW_PRIVATE_ENV, value)
    assert uu.allow_private() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "garbage"])
def test_private_refused_for_any_other_value(monkeypatch, value):
    monkeypatch.setenv(uu.ALLOW_PRIVATE_ENV, value)
    assert uu.allow_private() is False


@pytest.mark.parametrize("url", [*PRIVATE_URLS, "http://unstructured:8000/x"])
def test_default_allows_private_destinations(url):
    with _resolve_to() as resolve:
        assert uu.refusal_message(url) is None
    # No lookup is made when private destinations are allowed.
    resolve.assert_not_called()


@pytest.mark.parametrize(
    "url",
    ["ftp://10.0.0.5/x", "http://user:pass@10.0.0.5/x", "file:///etc/passwd"],
)
def test_default_still_applies_syntactic_checks(url):
    assert uu.refusal_message(url) is not None


@pytest.mark.parametrize("url", PRIVATE_URLS)
def test_block_mode_refuses_private_literals(monkeypatch, url):
    monkeypatch.setenv(uu.ALLOW_PRIVATE_ENV, "false")
    assert "private" in uu.refusal_message(url)


def test_block_mode_refuses_name_resolving_private(monkeypatch):
    monkeypatch.setenv(uu.ALLOW_PRIVATE_ENV, "false")
    with _resolve_to("10.1.2.3"):
        assert "private" in uu.refusal_message("http://unstructured.internal/x")


def test_block_mode_allows_public_name(monkeypatch):
    monkeypatch.setenv(uu.ALLOW_PRIVATE_ENV, "false")
    with _resolve_to("93.184.215.14"):
        assert (
            uu.refusal_message("https://api.unstructured.io/general/v0/general") is None
        )


def test_block_mode_unresolvable(monkeypatch):
    monkeypatch.setenv(uu.ALLOW_PRIVATE_ENV, "false")
    with _resolve_to():
        assert (
            uu.refusal_message("https://nope.invalid/x")
            == "Unstructured URL host could not be resolved"
        )


def test_default_timeout():
    assert uu.request_timeout() == (10.0, 900.0)


def test_timeout_override(monkeypatch):
    monkeypatch.setenv(uu.REQUEST_TIMEOUT_ENV, "1200")
    assert uu.request_timeout() == (10.0, 1200.0)


@pytest.mark.parametrize("value", ["abc", "0", "-5", "nan", "-inf"])
def test_invalid_timeout_falls_back(monkeypatch, value):
    monkeypatch.setenv(uu.REQUEST_TIMEOUT_ENV, value)
    assert uu.request_timeout() == (10.0, 900.0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("86400", 86400.0), ("86401", 86400.0), ("1e10", 86400.0), ("inf", 86400.0)],
)
def test_timeout_above_cap_is_clamped(monkeypatch, value, expected):
    monkeypatch.setenv(uu.REQUEST_TIMEOUT_ENV, value)
    assert uu.request_timeout() == (10.0, expected)


class _CookieThenRedirect(BaseHTTPRequestHandler):
    """/start sets a cookie and 302s to /done, which needs that cookie."""

    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(302)
        self.send_header("Set-Cookie", "sid=abc; Path=/")
        self.send_header("Location", "/done")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        ok = "sid=abc" in (self.headers.get("Cookie") or "")
        body = b"ok" if ok else b"no cookie"
        self.send_response(200 if ok else 403)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def test_block_mode_redirect_carries_cookie_set_by_earlier_hop(monkeypatch):
    monkeypatch.setenv(uu.ALLOW_PRIVATE_ENV, "false")
    server = HTTPServer(("127.0.0.1", 0), _CookieThenRedirect)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/start"
    try:
        # The guard is not under test here; let the loopback server through so
        # the checked-hop loop talks to a real HTTP stack.
        with mock.patch.object(uu, "webhook_url_refusal", return_value=None):
            r = uu.post(url, headers={}, data={"a": "b"}, files=lambda: None)
    finally:
        server.shutdown()
        server.server_close()
    assert (r.status_code, r.text) == (200, "ok")
