"""Tests for the SSRF-guarded webhook sender (spec §6.7).

``requests`` is patched at the ``webhook_notify`` import site; DNS is patched
inside ``unstract.core.network.ssrf``, which is where the egress decision now
lives (this module no longer has a resolver of its own -- Greptile review #4
replaced its hand-rolled ``_host_is_public`` with the shared guard). So no real
network/DNS activity occurs.

The behaviours asserted here are therefore the SINK's contract -- scheme
policy, the ``allow_insecure`` waiver, status-code handling, and the fact that
an unsafe destination never reaches ``requests.post``. The guard's own
address-classification rules are covered by
``unstract/core/tests/test_ssrf_guard.py``; the cases kept below are the ones
this sink must keep refusing regardless of which implementation is behind it.
"""

import socket
from unittest import mock

from shared.utils import webhook_notify as wn

from unstract.core.network import ssrf


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_private_ip_refused(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("10.0.0.5", 443))]
    assert wn.send_webhook("https://internal.example/x", {"a": 1}) is False
    assert not m_requests.post.called


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_metadata_ip_refused(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("169.254.169.254", 80))]
    assert wn.send_webhook("https://md.example/x", {}) is False


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_cgnat_shared_address_space_refused(m_gai, m_requests):
    """RFC 6598 100.64.0.0/10. `ipaddress.is_private` does not cover this
    range, which is why the old local guard needed a hand-maintained
    `_CGNAT_RANGE` constant for it (and why SonarCloud flagged that hardcoded
    address). The shared guard gets it from `is_global`, an allowlist kept
    against the IANA registries, so the range is covered without naming it.
    """
    m_gai.return_value = [(2, 1, 6, "", ("100.64.0.1", 443))]
    assert wn.send_webhook("https://cgnat.example/x", {}) is False
    assert not m_requests.post.called


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_nat64_embedded_loopback_refused(m_gai, m_requests):
    """``64:ff9b::7f00:1`` is the RFC 6052 NAT64 prefix carrying 127.0.0.1 in
    its low 32 bits; on a deployment with a NAT64 route, that is what gets
    dialled.

    A REGRESSION GUARD, not a fixed bug: the previous local guard refused this
    too, via ``ipaddress.is_reserved`` (checked on 3.12.9 -- the claim in
    Greptile review #4 that it was delivered to does not hold). It is pinned
    here because that refusal was incidental to a version-dependent flag,
    whereas the shared guard refuses it deliberately by re-checking the
    embedded IPv4. Both implementations pass; only one of them means to.
    """
    m_gai.return_value = [(socket.AF_INET6, 1, 6, "", ("64:ff9b::7f00:1", 443, 0, 0))]
    assert wn.send_webhook("https://nat64.example/x", {}) is False
    assert not m_requests.post.called


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_nat64_embedded_public_ip_still_allowed(m_gai, m_requests):
    """The companion to the test above, and the case that actually CHANGES
    behaviour.

    ``64:ff9b::5db8:d822`` embeds the public 93.184.216.34 -- a legitimate
    destination through a NAT64 translator. The old guard refused it, by the
    same blanket ``is_reserved`` that refused the loopback one: it could not
    tell the two apart, so it rejected the whole prefix. This test fails
    against that implementation and passes against the shared guard, which
    judges the embedded address.
    """
    m_gai.return_value = [(socket.AF_INET6, 1, 6, "", ("64:ff9b::5db8:d822", 443, 0, 0))]
    m_requests.post.return_value.status_code = 200
    assert wn.send_webhook("https://nat64-ok.example/hook", {}) is True


@mock.patch.object(wn, "requests")
def test_localhost_subdomain_refused_without_dns(m_requests):
    """RFC 6761 reserves ``*.localhost`` to loopback, and the shared guard
    decides that WITHOUT a resolver.

    No resolver is patched in this test, which is the point: the old guard had
    no such rule and could only reach the same answer through DNS, so its
    verdict depended on the image's libc (glibc's nss-myhostname answers for
    the whole subtree, musl only for the bare apex, a minimal container for
    neither). Same outcome, reached by luck rather than by rule.
    """
    assert wn.send_webhook("https://api.localhost/hook", {}) is False
    assert not m_requests.post.called


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_normal_public_ip_still_allowed(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
    m_requests.post.return_value.status_code = 200
    assert wn.send_webhook("https://cgnat-sibling.example/x", {}) is True


def test_http_scheme_refused_by_default():
    assert wn.send_webhook("http://example.com/x", {}) is False


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_public_host_posted_no_redirects(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
    m_requests.post.return_value.status_code = 200
    assert wn.send_webhook("https://example.com/hook", {"job_id": "j"}) is True
    kw = m_requests.post.call_args.kwargs
    assert kw["allow_redirects"] is False
    assert kw["timeout"] == 10


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_delivery_error_returns_false_never_raises(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
    m_requests.post.side_effect = Exception("boom")
    assert wn.send_webhook("https://example.com/hook", {}) is False


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_ipv6_loopback_refused(m_gai, m_requests):
    """Pins the 4-tuple IPv6 sockaddr shape: (addr, port, flowinfo, scope_id)."""
    m_gai.return_value = [(socket.AF_INET6, 1, 6, "", ("::1", 443, 0, 0))]
    assert wn.send_webhook("https://v6.example/x", {}) is False
    assert not m_requests.post.called


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_ipv6_public_posted(m_gai, m_requests):
    m_gai.return_value = [(socket.AF_INET6, 1, 6, "", ("2606:4700::1111", 443, 0, 0))]
    m_requests.post.return_value.status_code = 200
    assert wn.send_webhook("https://v6.example/hook", {}) is True


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_empty_resolution_refused(m_gai, m_requests):
    m_gai.return_value = []
    assert wn.send_webhook("https://nowhere.example/x", {}) is False
    assert not m_requests.post.called


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_multi_record_any_unsafe_refuses(m_gai, m_requests):
    """One public + one private record for the same host: must refuse (ALL
    resolved addresses must be public, not just the first).
    """
    m_gai.return_value = [
        (2, 1, 6, "", ("93.184.216.34", 443)),
        (2, 1, 6, "", ("10.0.0.5", 443)),
    ]
    assert wn.send_webhook("https://mixed.example/x", {}) is False
    assert not m_requests.post.called


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_server_error_status_returns_false(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
    m_requests.post.return_value.status_code = 500
    assert wn.send_webhook("https://example.com/hook", {}) is False


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_not_found_status_returns_false(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
    m_requests.post.return_value.status_code = 404
    assert wn.send_webhook("https://example.com/hook", {}) is False


@mock.patch.object(wn, "requests")
@mock.patch.object(ssrf.socket, "getaddrinfo")
def test_allow_http_true_posts_public_host(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 80))]
    m_requests.post.return_value.status_code = 200
    assert wn.send_webhook("http://example.com/hook", {}, allow_http=True) is True
    assert m_requests.post.called


class TestAllowInsecure:
    """``allow_insecure`` waives scheme + public-host guards (test stacks only)."""

    @mock.patch.object(wn, "requests")
    def test_http_private_host_delivered_when_insecure(self, m_requests):
        m_requests.post.return_value = mock.Mock(status_code=200)
        ok = wn.send_webhook(
            "http://host.docker.internal:18099/hook",
            {"job_id": "j", "status": "completed"},
            allow_insecure=True,
        )
        assert ok is True
        m_requests.post.assert_called_once()

    @mock.patch.object(wn, "requests")
    def test_default_still_refuses_http_and_private(self, m_requests):
        assert (
            wn.send_webhook("http://host.docker.internal:18099/hook", {"job_id": "j"})
            is False
        )
        assert not m_requests.post.called
