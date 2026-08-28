"""Tests for the SSRF-guarded webhook sender (spec §6.7).

``requests`` and ``socket.getaddrinfo`` are patched at the ``webhook_notify``
import site so no real network/DNS activity occurs.
"""

from unittest import mock

from shared.utils import webhook_notify as wn


@mock.patch.object(wn, "requests")
@mock.patch.object(wn.socket, "getaddrinfo")
def test_private_ip_refused(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("10.0.0.5", 443))]
    assert wn.send_webhook("https://internal.example/x", {"a": 1}) is False
    assert not m_requests.post.called


@mock.patch.object(wn, "requests")
@mock.patch.object(wn.socket, "getaddrinfo")
def test_metadata_ip_refused(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("169.254.169.254", 80))]
    assert wn.send_webhook("https://md.example/x", {}) is False


def test_http_scheme_refused_by_default():
    assert wn.send_webhook("http://example.com/x", {}) is False


@mock.patch.object(wn, "requests")
@mock.patch.object(wn.socket, "getaddrinfo")
def test_public_host_posted_no_redirects(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
    m_requests.post.return_value.status_code = 200
    assert wn.send_webhook("https://example.com/hook", {"job_id": "j"}) is True
    kw = m_requests.post.call_args.kwargs
    assert kw["allow_redirects"] is False
    assert kw["timeout"] == 10


@mock.patch.object(wn, "requests")
@mock.patch.object(wn.socket, "getaddrinfo")
def test_delivery_error_returns_false_never_raises(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
    m_requests.post.side_effect = Exception("boom")
    assert wn.send_webhook("https://example.com/hook", {}) is False
