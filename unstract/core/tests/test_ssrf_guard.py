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

from unstract.core.network.ssrf import (
    REFUSED_INTERNAL_LITERAL,
    REFUSED_NON_PUBLIC,
    REFUSED_SCHEME,
    REFUSED_UNPARSEABLE,
    UNRESOLVABLE,
    _normalize_host,
    is_retryable_refusal,
    is_safe_webhook_url,
    safe_host,
    webhook_url_refusal,
)
from unstract.core.notification_utils import send_webhook_request

_REAL_GETADDRINFO = socket.getaddrinfo

# Hosts the stub resolver answers for. Anything else fails to resolve.
_FAKE_DNS = {
    "example.com": {"93.184.216.34"},
    "webhook.site": {"46.4.105.116"},
    "internal.corp": {"10.0.0.5"},
    "rebind.test": {"93.184.216.34", "127.0.0.1"},
    "xn--e1afmkfd.xn--p1ai": {"93.184.216.34"},
    # UTS-46 forms of faß.de and σόλος.gr. The stdlib "idna" codec maps these
    # to fass.de and xn--wxaikc6b.gr instead, which is the bug the
    # normalization test below pins.
    "xn--fa-hia.de": {"93.184.216.34"},
    "xn--wxaijb9b.gr": {"93.184.216.34"},
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
        # IANA marks all of these as not globally reachable, but
        # ``ipaddress.is_global`` reports them as global on CPython 3.12, so
        # the guard has to refuse them itself. If a future CPython folds one of
        # these in, this test keeps passing.
        "https://224.0.0.1/hook",  # IPv4 multicast, all-hosts
        "https://239.255.255.250/hook",  # IPv4 multicast, SSDP
        "https://[ff02::1]/hook",  # IPv6 multicast, all-nodes
        "https://192.88.99.1/hook",  # 6to4 relay anycast
        "https://[5f00::1]/hook",  # SRv6 SIDs
    ],
)
def test_ranges_the_stdlib_calls_global_are_still_refused(url):
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


class TestWithoutResolution:
    """resolve=False keeps DNS off request-handling threads.

    getaddrinfo honours no timeout, so a slow resolver would stall the worker
    serving the request. The syntactic checks still run.
    """

    @pytest.mark.parametrize(
        "url",
        [
            "https://127.0.0.1/hook",
            "https://169.254.169.254/latest/meta-data/",
            "https://10.0.0.5/hook",
            "https://100.64.0.1/hook",
            "https://[::1]/hook",
            r"https://127.0.0.1:6666\@1.1.1.1",  # parsers disagree
            "https://user:pass@example.com/hook",  # credentials
            "ftp://example.com/hook",  # scheme
        ],
    )
    def test_literal_and_syntactic_cases_still_refused(self, url):
        assert is_safe_webhook_url(url, resolve=False) is False

    def test_no_lookup_is_issued(self, monkeypatch):
        def explode(*_a, **_k):
            raise AssertionError("DNS was resolved on a resolve=False call")

        monkeypatch.setattr("unstract.core.network.ssrf.socket.getaddrinfo", explode)
        assert is_safe_webhook_url("https://anything.internal/hook", resolve=False)

    def test_hostname_pointing_inward_is_left_to_the_sink(self):
        """Accepted here by design — the sink still resolves and refuses it."""
        assert is_safe_webhook_url("https://internal.corp/hook", resolve=False) is True
        assert is_safe_webhook_url("https://internal.corp/hook") is False


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
        # UTS-46, matching urllib3. The stdlib "idna" codec is IDNA-2003 and
        # would give "fass.de" and "xn--wxaikc6b.gr" — a host the transport
        # never dials, so the parser-agreement check would refuse both.
        ("faß.de", "xn--fa-hia.de"),
        ("σόλος.gr", "xn--wxaijb9b.gr"),
    ],
)
def test_normalize_host(raw, expected):
    assert _normalize_host(raw) == expected


@pytest.mark.parametrize("host", ["faß.de", "σόλος.gr", "пример.рф"])
def test_normalization_agrees_with_the_transport(host):
    """The two parsers must reduce a host the same way, or every IDN is refused.

    Pinned against urllib3 itself rather than a hardcoded expectation, so this
    fails if either encoder moves.
    """
    from urllib3.util import parse_url

    assert _normalize_host(host) == _normalize_host(parse_url(f"https://{host}/").host)
    assert is_safe_webhook_url(f"https://{host}/hook") is True


@pytest.mark.parametrize(
    "url",
    [
        "https://2130706433/hook",  # decimal
        "https://0177.0.0.1/hook",  # octal dotted
        "https://127.1/hook",  # short form
        "https://localhost/hook",  # RFC 6761, no lookup needed
        "https://api.localhost/hook",  # RFC 6761 reserves the whole subtree
        "https://DB.LocalHost/hook",  # case-insensitive after normalization
    ],
)
def test_legacy_loopback_encodings_are_refused_without_dns(url):
    """All of these are 127.0.0.1 to the resolver.

    ``ipaddress.ip_address`` parses none of the numeric forms, so on the
    no-resolve path they would otherwise be accepted as if they were
    hostnames — exactly the encodings used to slip a literal past a check.
    """
    assert is_safe_webhook_url(url, resolve=False) is False
    assert is_safe_webhook_url(url) is False


class TestRefusalReason:
    """Each sink needs the reason, not just the boolean.

    Without it a resolver outage and a genuinely internal target produce the
    same log line and the same error, and the delivery task cannot tell which
    of the two is worth retrying.
    """

    def test_public_url_has_no_reason(self):
        assert webhook_url_refusal("https://example.com/hook") is None

    def test_resolver_failure_is_reported_as_transient(self):
        assert webhook_url_refusal("https://nowhere.invalid/hook") == UNRESOLVABLE

    def test_internal_target_is_not_transient(self):
        assert webhook_url_refusal("https://internal.corp/hook") == REFUSED_NON_PUBLIC
        assert (
            webhook_url_refusal("https://127.0.0.1/hook", resolve=False)
            == REFUSED_INTERNAL_LITERAL
        )

    def test_reason_distinguishes_the_syntactic_checks(self):
        assert (
            webhook_url_refusal("http://example.com/hook", allowed_schemes=("https",))
            == REFUSED_SCHEME
        )


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

    def test_a_refused_url_is_marked_not_retryable(self):
        """The retry loop cannot change the answer, so it must not run.

        Every attempt would re-issue getaddrinfo for a tenant-supplied
        hostname and delay dead-lettering by up to max_retries × retry_delay.
        """
        with patch("unstract.core.notification_utils.requests.post"):
            result = send_webhook_request(url="https://internal.corp/hook", payload={})

        assert result["success"] is False
        assert result["retryable"] is False

    def test_a_resolver_outage_stays_retryable(self):
        """A blip is not a security refusal, and must not be reported as one."""
        with patch("unstract.core.notification_utils.requests.post"):
            result = send_webhook_request(url="https://nowhere.invalid/hook", payload={})

        assert result["success"] is False
        assert result["retryable"] is True
        assert result["refusal_reason"] == UNRESOLVABLE

    def test_a_url_that_breaks_urlparse_is_refused_not_raised(self):
        """The refusal log re-parses the URL; it must not raise doing so.

        ``urlparse("http://[::1")`` raises ValueError. ``webhook_url_refusal``
        catches that and returns REFUSED_UNPARSEABLE, so a second unguarded
        parse in the sink turned a deterministic refusal into an exception that
        the caller wraps as DeliveryError and retries like a transient failure.
        """
        with patch("unstract.core.notification_utils.requests.post") as post:
            result = send_webhook_request(url="http://[::1", payload={})

        post.assert_not_called()
        assert result["success"] is False
        assert result["retryable"] is False
        assert result["refusal_reason"] == REFUSED_UNPARSEABLE


class TestRetryabilityIsClassifiedOnce:
    """Every sink asks the guard whether a refusal can clear, rather than
    re-deriving it — a new reason has to be classified in one place."""

    def test_only_a_resolver_outage_is_retryable(self):
        assert is_retryable_refusal(UNRESOLVABLE) is True
        for reason in (
            REFUSED_INTERNAL_LITERAL,
            REFUSED_NON_PUBLIC,
            REFUSED_SCHEME,
            REFUSED_UNPARSEABLE,
        ):
            assert is_retryable_refusal(reason) is False

    def test_no_refusal_is_not_retryable(self):
        assert is_retryable_refusal(None) is False

    def test_safe_host_never_raises_and_never_leaks_the_query_string(self):
        assert safe_host("https://example.com/hook?token=secret") == "example.com"
        assert safe_host("http://[::1") == "<unparseable>"
        assert safe_host(None) == "<none>"
