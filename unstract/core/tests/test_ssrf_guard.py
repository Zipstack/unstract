"""Tests for the shared webhook egress guard.

The parser-differential cases are URLs where ``urlparse`` and ``urllib3``
disagree on the host, in both directions. The IPv6/IDN cases are the false
positives a naive string compare of the two hosts produces — those are
legitimate targets and must still be allowed.

DNS is stubbed so the suite does not depend on the network; the resolver is
exercised separately through the public-address cases.
"""

import socket
from unittest.mock import patch

import pytest

from unstract.core.network.ssrf import _normalize_host, is_safe_webhook_url
from unstract.core.notification_utils import send_webhook_request

_REAL_GETADDRINFO = socket.getaddrinfo

# Hosts the stub resolver answers for. Anything else fails to resolve.
_FAKE_DNS = {
    "example.com": {"93.184.216.34"},
    "webhook.site": {"46.4.105.116"},
    "internal.corp": {"10.0.0.5"},
    "rebind.test": {"93.184.216.34", "127.0.0.1"},
    "xn--e1afmkfd.xn--p1ai": {"93.184.216.34"},
}


@pytest.fixture(autouse=True)
def stub_dns(monkeypatch):
    def fake_getaddrinfo(host, *_args, **_kwargs):
        if host not in _FAKE_DNS:
            raise OSError(f"unresolvable in test: {host}")
        return [(None, None, None, "", (addr, 0)) for addr in _FAKE_DNS[host]]

    monkeypatch.setattr("unstract.core.network.ssrf.socket.getaddrinfo", fake_getaddrinfo)


@pytest.mark.parametrize(
    "url",
    [
        # urlparse reads 1.1.1.1 here; urllib3 connects to 127.0.0.1.
        r"https://127.0.0.1:6666\@1.1.1.1",
        # The differential runs both ways.
        r"https://1.1.1.1:80\@127.0.0.1/",
    ],
)
def test_parser_differential_is_refused(url):
    assert is_safe_webhook_url(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/hook",
        "https://localhost/hook",
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata
        "https://[::1]/hook",
        "https://10.0.0.5/hook",
        "https://192.168.1.1/hook",
        "https://172.16.0.1/hook",
        "https://0.0.0.0/hook",
        "https://internal.corp/hook",
        # Ranges that belong to no single "is_private"-style flag but are not
        # globally routable. Enumerating negative flags misses these.
        "https://100.64.0.1/hook",  # RFC 6598 shared address space (CGNAT)
        "https://198.18.0.1/hook",  # RFC 2544 benchmarking
        "https://192.0.0.1/hook",  # IETF protocol assignments
    ],
)
def test_internal_targets_are_refused(url):
    assert is_safe_webhook_url(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/hook",
        "file:///etc/passwd",
        "gopher://example.com/",
        "https://user:pass@example.com/hook",  # credentials in URL
        "not-a-url",
        "",
        None,
    ],
)
def test_malformed_and_disallowed_schemes_are_refused(url):
    assert is_safe_webhook_url(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/hook",
        "https://webhook.site/abc-123",
        "https://example.com./hook",  # trailing dot
        "https://EXAMPLE.com/hook",  # uppercase host
        "https://xn--e1afmkfd.xn--p1ai/hook",  # punycode IDN
        "https://пример.рф/hook",  # raw unicode IDN, same host
    ],
)
def test_public_targets_are_allowed(url):
    assert is_safe_webhook_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://" + "a" * 64 + ".com/hook",  # label over the 63-char limit
        "https://ex..ample.com/hook",  # empty label
    ],
)
def test_unresolvable_hosts_return_false_rather_than_raising(url, monkeypatch):
    """getaddrinfo raises UnicodeError on these instead of failing to resolve.

    Callers treat this as a boolean check, so an escaping exception becomes a
    500 in the notification serializer and an error in the delivery task.

    Runs against the real resolver: the failure is inside getaddrinfo, so the
    stub above would make this pass for the wrong reason. No lookup is issued
    — both hosts are rejected before any query goes out.
    """
    monkeypatch.setattr(
        "unstract.core.network.ssrf.socket.getaddrinfo", _REAL_GETADDRINFO
    )
    assert is_safe_webhook_url(url) is False


def test_any_internal_address_in_a_multi_answer_rrset_refuses():
    """A host that also answers with a loopback address is not safe."""
    assert is_safe_webhook_url("https://rebind.test/hook") is False


def test_http_is_allowed_by_default_but_not_for_tls_only_callers():
    assert is_safe_webhook_url("http://example.com/hook") is True
    assert (
        is_safe_webhook_url("http://example.com/hook", allowed_schemes=("https",))
        is False
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("[::1]", "::1"),
        ("EXAMPLE.com.", "example.com"),
        ("пример.рф", "xn--e1afmkfd.xn--p1ai"),
        (None, ""),
    ],
)
def test_normalize_host(raw, expected):
    assert _normalize_host(raw) == expected


class TestNotificationSink:
    """The guard sits inside ``send_webhook_request`` so no caller can skip it.

    Redirects are off on this path as well: a 302 to an internal host would
    otherwise be followed, and 302/303 rewrites POST to GET.
    """

    @pytest.mark.parametrize(
        "url",
        [
            "https://169.254.169.254/latest/meta-data/",
            "https://127.0.0.1:8000/admin/",
            r"https://127.0.0.1:6666\@1.1.1.1",
        ],
    )
    def test_blocked_url_never_reaches_the_network(self, url):
        with patch("unstract.core.notification_utils.requests.post") as post:
            result = send_webhook_request(url=url, payload={"payload": 1})
        post.assert_not_called()
        assert result["success"] is False

    def test_redirects_are_not_followed(self):
        with patch("unstract.core.notification_utils.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.text = "ok"
            send_webhook_request(url="https://example.com/hook", payload={})

        assert post.call_args.kwargs["allow_redirects"] is False

    def test_public_url_is_still_delivered(self):
        with patch("unstract.core.notification_utils.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.text = "ok"
            result = send_webhook_request(url="https://example.com/hook", payload={})

        post.assert_called_once()
        assert result["success"] is True
