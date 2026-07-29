"""Webhook URL egress controls on the backend side.

The sink guard in ``unstract.core`` is the real control; these cover the two
backend surfaces that also accept a URL — the notification serializer, which
should refuse an internal target at creation rather than at delivery time, and
the internal webhook-test endpoint, which used to return the response body.
"""

from unittest.mock import Mock, patch

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
        assert "response_body" not in response.data
        assert "response_headers" not in response.data
        assert response.data["status_code"] == 200
        assert post.call_args.kwargs["allow_redirects"] is False

    def test_redirect_is_not_reported_as_success(self):
        """Redirects are not followed, so a 3xx means the payload never landed."""
        with patch("requests.post") as post:
            post.return_value.status_code = 302
            post.return_value.headers = {}
            post.return_value.text = ""
            response = self._post("https://example.com/hook")

        assert response.data["status_code"] == 302
        assert response.data["success"] is False
