"""Request-level tests for /logout.

GET is v0's sign-out and answers with the auth service's redirect. POST is
v1's: DRF's SessionAuthentication enforces CSRF on it for a signed-in user, and
it answers 200 with that redirect's target, which a script caller can open
itself. The URL whitelist, the session and the CSRF
check all sit outside the view, so these go through the URLconf and the shipped
middleware with the real AuthenticationController.
"""

import secrets
from contextlib import AbstractContextManager
from unittest.mock import patch

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.test import Client, TestCase

from account_v2.models import User

LOGOUT_URL = f"/{settings.PATH_PREFIX}/logout"
# Shaped like the cloud auth plugin's answer: a cross-origin identity-provider
# sign-out that a fetch or XHR caller cannot follow.
IDP_LOGOUT_URL = "https://id.example.com/v2/logout?returnTo=https%3A%2F%2Fapp.example.com"


class LogoutEndpointTests(TestCase):
    def setUp(self) -> None:
        for target, value in (
            # Redis log cleanup, keyed by session; nothing to clean here.
            (
                "account_v2.authentication_controller.LogService.remove_logs_on_logout",
                None,
            ),
            # Pin the built-in auth service, as a cloud build installs a plugin.
            (
                "account_v2.authentication_plugin_registry."
                "AuthenticationPluginRegistry.is_plugin_available",
                False,
            ),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        user = User.objects.create_user(
            username="member@example.com",
            email="member@example.com",
            password=secrets.token_urlsafe(),
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(user)

    def _send(self, method: str, csrf: bool = True) -> HttpResponse:
        headers = {}
        if csrf:
            token = secrets.token_hex(16)
            self.client.cookies[settings.CSRF_COOKIE_NAME] = token
            headers["HTTP_X_CSRFTOKEN"] = token
        return getattr(self.client, method)(LOGOUT_URL, **headers)

    def _signed_in(self) -> bool:
        return "_auth_user_id" in self.client.session

    def _idp_logout(self) -> AbstractContextManager:
        response = HttpResponseRedirect(IDP_LOGOUT_URL)
        response.delete_cookie("idp_hint")
        return patch(
            "account_v2.authentication_controller.AuthenticationService.user_logout",
            return_value=response,
        )

    def test_get_redirects_and_ends_session(self) -> None:
        response = self.client.get(LOGOUT_URL)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], settings.WEB_APP_ORIGIN_URL)
        self.assertFalse(self._signed_in())

    def test_post_with_csrf_token_returns_redirect_url_and_ends_session(self) -> None:
        response = self._send("post")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"redirect_url": settings.WEB_APP_ORIGIN_URL})
        self.assertFalse(self._signed_in())

    def test_get_passes_identity_provider_redirect_through(self) -> None:
        with self._idp_logout():
            response = self.client.get(LOGOUT_URL)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], IDP_LOGOUT_URL)
        self.assertFalse(self._signed_in())

    def test_post_returns_identity_provider_url_with_its_cookies(self) -> None:
        with self._idp_logout():
            response = self._send("post")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"redirect_url": IDP_LOGOUT_URL})
        self.assertIn("idp_hint", response.cookies)
        self.assertFalse(self._signed_in())

    def test_post_without_csrf_token_is_refused_and_keeps_session(self) -> None:
        response = self._send("post", csrf=False)
        self.assertEqual(response.status_code, 403)
        self.assertIn("CSRF", response.content.decode())
        self.assertTrue(self._signed_in())

    def test_other_methods_are_refused_and_keep_session(self) -> None:
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(self._send(method).status_code, 405)
                self.assertTrue(self._signed_in())
