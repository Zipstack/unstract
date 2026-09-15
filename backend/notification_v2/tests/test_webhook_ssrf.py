"""Webhook URL egress controls on the backend side.

The sink guard in ``unstract.core`` is the real control; these cover the two
backend surfaces that also accept a URL — the notification serializer, which
should refuse an internal target at creation rather than at delivery time, and
the internal webhook-test endpoint, which used to return the response body.
"""

from unittest.mock import Mock, patch

import pytest
import requests
from django.test import SimpleTestCase
from notification_v2.internal_views import WebhookTestAPIView
from notification_v2.serializers import NotificationSerializer
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

INTERNAL_URLS = [
    "http://169.254.169.254/latest/meta-data/",
    "http://127.0.0.1:8000/admin/",
    r"https://127.0.0.1:6666\@1.1.1.1",
]

# Stub DNS so nothing here depends on the network. The serializer path does not
# resolve at all; the endpoint path does, and would otherwise make a real
# lookup for example.com and fail in an isolated runner.
_FAKE_DNS = {"example.com": "93.184.216.34"}


@pytest.fixture(autouse=True)
def stub_dns(monkeypatch):
    def fake_getaddrinfo(host, *_args, **_kwargs):
        if host not in _FAKE_DNS:
            raise OSError(f"unresolvable in test: {host}")
        return [(None, None, None, "", (_FAKE_DNS[host], 0))]

    monkeypatch.setattr(
        "unstract.core.network.ssrf.socket.getaddrinfo", fake_getaddrinfo
    )


def _notification_data(url):
    """Minimum that reaches the URL check in ``NotificationSerializer.validate``."""
    return {"pipeline": Mock(), "authorization_type": "NONE", "url": url}


class NotificationSerializerUrlTest(SimpleTestCase):
    """URLField only checks the shape, so an internal target would persist."""

    def test_internal_urls_are_rejected(self):
        for url in INTERNAL_URLS:
            with self.subTest(url=url):
                with self.assertRaises(ValidationError) as caught:
                    NotificationSerializer().validate(_notification_data(url))
                assert "url" in caught.exception.detail

    def test_public_url_is_accepted(self):
        data = _notification_data("https://example.com/hook")
        assert NotificationSerializer().validate(data) == data

    def test_webhook_create_without_a_url_is_rejected(self):
        """``url`` is null=True on the model, so DRF makes it optional.

        Without this check a webhook notification persists with no destination
        and returns 201; at dispatch the user is told the URL "is not an
        allowed public destination" for a URL that was never set.
        """
        for data in (
            # omitted entirely
            {
                "pipeline": Mock(),
                "authorization_type": "NONE",
                "notification_type": "WEBHOOK",
            },
            # explicitly null
            {
                "pipeline": Mock(),
                "authorization_type": "NONE",
                "notification_type": "WEBHOOK",
                "url": None,
            },
        ):
            with self.subTest(data=sorted(data)):
                with self.assertRaises(ValidationError) as caught:
                    NotificationSerializer().validate(data)
                assert "url" in caught.exception.detail

    def test_webhook_patch_that_omits_url_keeps_the_stored_one(self):
        """The create check must not break the documented PATCH case."""
        instance = Mock(api=None, notification_type="WEBHOOK", url="https://a.example")
        serializer = NotificationSerializer(instance=instance, partial=True)

        data = {"pipeline": Mock(), "authorization_type": "NONE", "max_retries": 2}
        assert serializer.validate(data) == data

    def test_patch_switching_a_url_less_record_to_webhook_is_rejected(self):
        """``self.partial`` alone is the wrong gate for the required-URL check.

        Turning an existing URL-less notification into a WEBHOOK creates a
        destination-less webhook just as surely as a create does, so the type
        change has to be checked as well as ``partial``.
        """
        instance = Mock(api=None, notification_type="EMAIL", url=None)
        serializer = NotificationSerializer(instance=instance, partial=True)

        data = {
            "pipeline": Mock(),
            "authorization_type": "NONE",
            "notification_type": "WEBHOOK",
        }
        with self.assertRaises(ValidationError) as caught:
            serializer.validate(data)
        assert "url" in caught.exception.detail

    def test_patch_that_omits_url_is_not_revalidated(self):
        """A PATCH touching other fields must not re-resolve the stored URL.

        Otherwise a brief DNS failure, or a record predating this check, makes
        an unrelated edit fail on a field the caller never sent.
        """
        # api=None so the api/pipeline check doesn't trip on Mock's truthy
        # auto-attribute before the URL check is reached.
        instance = Mock(api=None, url="http://127.0.0.1:8000/legacy")
        serializer = NotificationSerializer(instance=instance)

        data = {"pipeline": Mock(), "authorization_type": "NONE", "max_retries": 2}
        assert serializer.validate(data) == data


class WebhookTestEndpointTest(SimpleTestCase):
    """This endpoint had no URL check, and returned the response body."""

    def _post(self, url):
        request = Request(
            APIRequestFactory().post(
                "/internal/webhook/test/", {"url": url, "payload": {}}, format="json"
            ),
            parsers=[JSONParser()],
        )
        return WebhookTestAPIView().post(request)

    def test_internal_url_is_refused_before_any_request(self):
        for url in INTERNAL_URLS:
            with self.subTest(url=url):
                with patch("requests.post") as post:
                    response = self._post(url)
                assert response.status_code == status.HTTP_400_BAD_REQUEST
                post.assert_not_called()

    def test_response_body_and_headers_are_not_echoed(self):
        with patch("requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.headers = {"X-Internal-Secret": "leaked"}
            post.return_value.text = "internal response body"
            response = self._post("https://example.com/hook")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status_code"] == 200
        assert post.call_args.kwargs["allow_redirects"] is False

        # Nothing about the upstream response comes back, and neither do the
        # request headers — those carry the Authorization value we built.
        for leaked in ("response_body", "response_headers", "request_headers"):
            assert leaked not in response.data, f"{leaked} is echoed to the caller"

    def test_transport_failure_does_not_echo_the_authorization_header(self):
        """The error branch is the common path, and it built the credential.

        A public host that simply does not answer never reaches the guard, so
        this is reachable for any well-formed URL. The success-branch test
        above cannot catch it: it only stubs a 200.
        """
        request = Request(
            APIRequestFactory().post(
                "/internal/webhook/test/",
                {
                    "url": "https://example.com/hook",
                    "payload": {},
                    "authorization_type": "BEARER",
                    "authorization_key": "super-secret-token",
                },
                format="json",
            ),
            parsers=[JSONParser()],
        )
        with patch("requests.post") as post:
            post.side_effect = requests.exceptions.ConnectTimeout("timed out")
            response = WebhookTestAPIView().post(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["success"] is False
        for leaked in ("request_headers", "request_payload"):
            assert leaked not in response.data, f"{leaked} is echoed to the caller"
        assert "super-secret-token" not in str(response.data)

    def test_redirect_is_not_reported_as_success(self):
        """Redirects are not followed, so a 3xx means the payload never landed."""
        with patch("requests.post") as post:
            post.return_value.status_code = 302
            post.return_value.headers = {}
            post.return_value.text = ""
            response = self._post("https://example.com/hook")

        assert response.data["status_code"] == 302
        assert response.data["success"] is False


class UrlLessWebhookRowTest(SimpleTestCase):
    """A stored webhook with no URL is invalid however it got that way."""

    def test_patch_on_a_url_less_webhook_row_is_rejected(self):
        """Even when the PATCH is about something else entirely.

        Gating on `partial` let a legacy WEBHOOK row with url=None survive an
        unrelated edit and stay undeliverable. Gating on the stored URL does
        not, and leaves rows that already have one alone.
        """
        instance = Mock(api=None, notification_type="WEBHOOK", url=None)
        serializer = NotificationSerializer(instance=instance, partial=True)

        data = {"pipeline": Mock(), "authorization_type": "NONE", "max_retries": 2}
        with self.assertRaises(ValidationError) as caught:
            serializer.validate(data)
        assert "url" in caught.exception.detail
