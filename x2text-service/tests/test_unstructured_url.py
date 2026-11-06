"""The unstructured-url egress guard and the timeout setting."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import pytest
import requests
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
    monkeypatch.delenv(uu.ALLOWED_HOSTS_ENV, raising=False)


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
    [
        "ftp://10.0.0.5/x",
        "file:///etc/passwd",
        "http://user:pass@a\x00b/x",
        "http://user:pass@[abc/x",
    ],
)
def test_default_still_applies_syntactic_checks(url):
    assert uu.refusal_message(url) is not None


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pass@10.0.0.5:8000/general/v0/general",
        "https://user:pass@unstructured.example.com/general/v0/general",
        "http://user@localhost:8000/x",
    ],
)
def test_default_allows_credentials_in_url(url):
    # Basic auth in front of a self-hosted Unstructured worked before the guard.
    with _resolve_to() as resolve:
        assert uu.refusal_reason(url) is None
    resolve.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        # urlparse reads host c, the transport dials b.
        "http://a@b\\@c/x",
        # urlparse drops the tab, the transport keeps it.
        "http://u@exa\tmple.com/x",
        # The transport cannot parse it, so the copy cannot be vouched for.
        "http://u@host:99999/x",
    ],
)
def test_default_refuses_credentials_that_change_the_dialled_host(url):
    assert uu.refusal_reason(url) == "credentials-in-url"


def test_block_mode_refuses_credentials_in_url(monkeypatch):
    monkeypatch.setenv(uu.ALLOW_PRIVATE_ENV, "false")
    with _resolve_to("93.184.216.34"):
        assert uu.refusal_reason("https://user:pass@example.com/x") == (
            "credentials-in-url"
        )


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


IN_CLUSTER = "http://unstract-unstructured-io:8000/general/v0/general"


@pytest.fixture
def block_private(monkeypatch):
    monkeypatch.setenv(uu.ALLOW_PRIVATE_ENV, "false")


def test_block_mode_allows_allowlisted_private_host(monkeypatch, block_private):
    monkeypatch.setenv(uu.ALLOWED_HOSTS_ENV, "unstract-unstructured-io")
    with _resolve_to("10.96.0.12") as resolve:
        assert uu.refusal_message(IN_CLUSTER) is None
    # The destination check is skipped, so no lookup is made for it.
    resolve.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "http://unstructured.internal/x",
        # Exact match only: neither a subdomain of an entry nor a name that
        # begins with one.
        "http://evil.unstract-unstructured-io/x",
        "http://unstract-unstructured-io.attacker.example/x",
    ],
)
def test_block_mode_refuses_private_host_not_allowlisted(monkeypatch, block_private, url):
    monkeypatch.setenv(uu.ALLOWED_HOSTS_ENV, "unstract-unstructured-io")
    with _resolve_to("10.1.2.3"):
        assert "private" in uu.refusal_message(url)


@pytest.mark.parametrize(
    "value",
    [
        "UNSTRACT-Unstructured-IO",
        "  unstract-unstructured-io  ",
        "other-svc , Unstract-Unstructured-Io ,",
    ],
)
def test_allowlist_is_trimmed_and_case_insensitive(monkeypatch, block_private, value):
    monkeypatch.setenv(uu.ALLOWED_HOSTS_ENV, value)
    with _resolve_to("10.96.0.12"):
        assert uu.refusal_message(IN_CLUSTER) is None


def test_allowlist_matches_url_host_case_insensitively(monkeypatch, block_private):
    # Saved adapter URLs can carry upper case in the host.
    monkeypatch.setenv(uu.ALLOWED_HOSTS_ENV, "unstract-unstructured-io")
    with _resolve_to("10.96.0.12"):
        assert uu.refusal_message("http://Unstract-Unstructured-IO:8000/x") is None


def test_refusal_log_shows_allowlist_so_a_bad_entry_is_visible(
    monkeypatch, block_private, caplog
):
    # A port never matches a hostname; the log is where an operator sees it.
    monkeypatch.setenv(uu.ALLOWED_HOSTS_ENV, "zz-svc, unstract-unstructured-io:8000")
    with _resolve_to("10.96.0.12"):
        assert "private" in uu.refusal_message(IN_CLUSTER)
    # Sorted, so the line is stable across runs.
    assert f"{uu.ALLOWED_HOSTS_ENV}=unstract-unstructured-io:8000,zz-svc" in caplog.text


@pytest.mark.parametrize("value", [None, "", " ", ",, ,"])
def test_empty_allowlist_keeps_block_behaviour(monkeypatch, block_private, value):
    if value is not None:
        monkeypatch.setenv(uu.ALLOWED_HOSTS_ENV, value)
    assert uu.allowed_hosts() == frozenset()
    with _resolve_to("10.96.0.12"):
        assert "private" in uu.refusal_message(IN_CLUSTER)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://unstract-unstructured-io/x",
        "http://user:pass@unstract-unstructured-io/x",
    ],
)
def test_allowlisted_host_still_gets_syntactic_checks(monkeypatch, block_private, url):
    monkeypatch.setenv(uu.ALLOWED_HOSTS_ENV, "unstract-unstructured-io")
    assert uu.refusal_message(url) is not None


def test_allowlist_irrelevant_when_private_allowed(monkeypatch):
    monkeypatch.setenv(uu.ALLOWED_HOSTS_ENV, "unstract-unstructured-io")
    with _resolve_to("10.1.2.3") as resolve:
        assert uu.refusal_message("http://unstructured.internal/x") is None
        assert uu.refusal_message(IN_CLUSTER) is None
    resolve.assert_not_called()


def _response(status, location=None):
    r = requests.models.Response()
    r.status_code = status
    r._content = b""
    r._content_consumed = True
    if location is not None:
        r.headers["Location"] = location
    return r


def test_redirect_from_allowlisted_to_other_private_host_is_refused(
    monkeypatch, block_private
):
    monkeypatch.setenv(uu.ALLOWED_HOSTS_ENV, "unstract-unstructured-io")
    hop = _response(307, "http://unstructured.internal/x")
    with (
        _resolve_to("10.1.2.3"),
        mock.patch.object(requests.Session, "request", return_value=hop) as rq,
        pytest.raises(uu.RedirectNotAllowed),
    ):
        uu.post(IN_CLUSTER, headers={}, data={}, files=lambda: None)
    # The allowlisted origin is dialled; the private hop never is.
    assert rq.call_count == 1
    assert rq.call_args.args[1] == IN_CLUSTER


def test_redirect_within_allowlisted_host_is_followed(monkeypatch, block_private):
    monkeypatch.setenv(uu.ALLOWED_HOSTS_ENV, "unstract-unstructured-io")
    with (
        _resolve_to("10.96.0.12"),
        mock.patch.object(
            requests.Session,
            "request",
            side_effect=[
                _response(307, "/general/v0/general?retry=1"),
                _response(200),
            ],
        ) as rq,
    ):
        r = uu.post(IN_CLUSTER, headers={}, data={}, files=lambda: None)
    assert r.status_code == 200
    assert rq.call_args.args[1] == IN_CLUSTER + "?retry=1"


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
