"""CustomAuthMiddleware hands out the session's log channel, not its key.

``log_events_id`` reaches API responses (``/organization/<org>/set``), workflow
executions, worker payloads and log lines. The session key is the HttpOnly
cookie's value, so it must never be what the middleware stores there. And the
socket server must join the room the middleware names, or live logs stop.

DB-backed Django ``TestCase`` -> auto-marked ``integration`` by
``backend/conftest.py``.
"""

import secrets
from unittest.mock import patch

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.test import override_settings
from django.urls import path
from rest_framework.test import APIClient, APITestCase
from utils import log_events
from utils.local_context import StateStore
from utils.log_channel import log_channel_id

from account_v2.constants import Common
from account_v2.models import Organization, User

ORG = "org-a"
PROBE_URL = f"/api/v1/unstract/{ORG}/log-channel-probe/"


def _probe(request: HttpRequest) -> JsonResponse:
    """What a view sees as the request's log channel, as `/set` returns it."""
    return JsonResponse({Common.LOG_EVENTS_ID: StateStore.get(Common.LOG_EVENTS_ID)})


# OrganizationMiddleware strips the org segment before routing.
urlpatterns = [path("api/v1/unstract/log-channel-probe/", _probe)]

_MIDDLEWARE = [
    "middleware.request_id.CustomRequestIDMiddleware",
    settings.TENANT_MIDDLEWARE,
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    settings.CUSTOM_AUTH_MIDDLEWARE,
]


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=_MIDDLEWARE)
class LogChannelMiddlewareTest(APITestCase):
    def setUp(self) -> None:
        Organization.objects.create(name=ORG, display_name="Org A", organization_id=ORG)
        registry = patch(
            "account_v2.custom_auth_middleware."
            "AuthenticationPluginRegistry.is_plugin_available",
            return_value=False,
        )
        registry.start()
        self.addCleanup(registry.stop)
        renew = patch("account_v2.session_tracking._renew_session_sockets")
        renew.start()
        self.addCleanup(renew.stop)

    def _sign_in(self, email: str) -> APIClient:
        user = User.objects.create_user(
            username=email, email=email, password=secrets.token_urlsafe()
        )
        client = APIClient()
        client.force_login(user)
        session = client.session
        session["organization"] = ORG
        session["user_id"] = str(user.pk)
        session.save()
        return client

    @staticmethod
    def _session_key(client: APIClient) -> str:
        return client.cookies[settings.SESSION_COOKIE_NAME].value

    def test_the_request_log_channel_is_derived_from_the_session(self) -> None:
        client = self._sign_in("alice@example.com")

        response = client.get(PROBE_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()[Common.LOG_EVENTS_ID],
            log_channel_id(self._session_key(client)),
        )

    def test_the_session_key_is_not_in_the_response(self) -> None:
        client = self._sign_in("alice@example.com")

        response = client.get(PROBE_URL)

        self.assertNotIn(self._session_key(client), response.content.decode())

    def test_each_session_has_its_own_channel(self) -> None:
        alice = self._sign_in("alice@example.com")
        bob = self._sign_in("bob@example.com")

        alice_channel = alice.get(PROBE_URL).json()[Common.LOG_EVENTS_ID]
        bob_channel = bob.get(PROBE_URL).json()[Common.LOG_EVENTS_ID]

        self.assertNotEqual(alice_channel, bob_channel)

    def test_the_socket_joins_the_room_the_middleware_names(self) -> None:
        # The frontend listens on the id `/set` returns; logs reach it only if
        # the socket server put the session's socket in that same room.
        client = self._sign_in("alice@example.com")
        channel = client.get(PROBE_URL).json()[Common.LOG_EVENTS_ID]
        environ = {
            "HTTP_COOKIE": f"{settings.SESSION_COOKIE_NAME}={self._session_key(client)}"
        }

        with (
            patch.object(log_events, "_track_session_socket", return_value=True),
            patch.object(log_events, "_get_user_id", return_value=None),
            patch.object(log_events.sio, "enter_room") as enter_room,
        ):
            log_events.connect("sid-1", environ, None)

        enter_room.assert_called_once_with("sid-1", channel)
