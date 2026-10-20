"""Signed-in sessions: recording, listing and revoking through the real chain.

Revocation only means something if the next request on the revoked session is
refused, which `CustomAuthMiddleware` decides before any view runs, so these
tests drive two independent clients through a trimmed production middleware
chain rather than calling the views directly.
"""

import secrets
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.urls import include, path
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APITestCase

from account_v2.models import Organization, SessionRecord, User
from account_v2.session_tracking import (
    _TOUCH_CACHE_PREFIX,
    SessionTracker,
    _location_resolver,
    _recording_started_at,
    parse_user_agent,
)
from account_v2.session_views import _require_browser_session

ORG = "org-a"
SESSIONS_URL = f"/api/v1/unstract/{ORG}/users/sessions/"
REVOKE_ALL_URL = f"{SESSIONS_URL}revoke-all/"
CHROME_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
FIREFOX_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0"
)

# OrganizationMiddleware strips the org segment before routing.
urlpatterns = [path("api/v1/unstract/users/", include("tenant_account_v2.users_urls"))]

# Trimmed from the production chain, preserving its relative order.
_MIDDLEWARE = [
    "middleware.request_id.CustomRequestIDMiddleware",
    settings.TENANT_MIDDLEWARE,
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    settings.CUSTOM_AUTH_MIDDLEWARE,
]


def resolve_test_location(ip_address: str) -> str:
    return f"near {ip_address}"


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=_MIDDLEWARE)
class SessionEndpointsTest(APITestCase):
    def setUp(self) -> None:
        Organization.objects.create(name=ORG, display_name="Org A", organization_id=ORG)
        self.user = self._make_user("alice@example.com")
        registry = patch(
            "account_v2.custom_auth_middleware."
            "AuthenticationPluginRegistry.is_plugin_available",
            return_value=False,
        )
        registry.start()
        self.addCleanup(registry.stop)

    @staticmethod
    def _make_user(email: str) -> User:
        return User.objects.create_user(
            username=email, email=email, password=secrets.token_urlsafe()
        )

    @staticmethod
    def _sign_in(user: User, user_agent: str = CHROME_MAC) -> APIClient:
        """A browser signed in to ORG, as the auth flows leave the session."""
        client = APIClient(HTTP_USER_AGENT=user_agent)
        client.force_login(user)
        session = client.session
        session["organization"] = ORG
        session["user_id"] = str(user.pk)
        session.save()
        # `force_login` signs in on a bare request with no headers; a browser's
        # sign-in request carries its user agent.
        SessionRecord.objects.filter(
            session_key=client.cookies[settings.SESSION_COOKIE_NAME].value
        ).update(user_agent=user_agent)
        return client

    @staticmethod
    def _key(client: APIClient) -> str:
        return client.cookies[settings.SESSION_COOKIE_NAME].value

    def test_sign_in_records_the_session(self) -> None:
        client = self._sign_in(self.user)

        record = SessionRecord.objects.get(session_key=self._key(client))
        self.assertEqual(record.user, self.user)

    def test_list_shows_both_sessions_with_the_right_current_one(self) -> None:
        laptop = self._sign_in(self.user, CHROME_MAC)
        desktop = self._sign_in(self.user, FIREFOX_WINDOWS)
        desktop.get(SESSIONS_URL)  # Desktop is now the most recently active.

        response = laptop.get(SESSIONS_URL)

        self.assertEqual(response.status_code, 200)
        sessions = response.json()
        self.assertEqual(len(sessions), 2)
        current, other = sessions
        self.assertTrue(current["is_current"])
        self.assertFalse(other["is_current"])
        self.assertEqual(
            str(SessionRecord.objects.get(session_key=self._key(laptop)).id),
            current["id"],
        )
        self.assertEqual(
            set(current),
            {
                "id",
                "browser",
                "os",
                "device_label",
                "location",
                "last_active",
                "created",
                "is_current",
            },
        )
        self.assertIsNone(current["location"])
        self.assertEqual(current["device_label"], "Chrome on macOS")
        self.assertEqual(
            (other["browser"], other["os"], other["device_label"]),
            ("Firefox", "Windows", "Firefox on Windows"),
        )

    def test_signing_in_as_someone_else_on_one_browser_records_the_new_user(
        self,
    ) -> None:
        browser = self._sign_in(self.user)
        alice_key = self._key(browser)
        bob = self._make_user("bob@example.com")

        # A different user signing in flushes the session instead of cycling it.
        browser.force_login(bob)

        bob_key = self._key(browser)
        self.assertNotEqual(bob_key, alice_key)
        self.assertEqual(SessionRecord.objects.get(session_key=bob_key).user, bob)
        # Alice's flushed session is gone, so it is no longer one of hers.
        self.assertEqual(SessionTracker.live_records(self.user), [])

    def _expire(self, client: APIClient) -> None:
        Session.objects.filter(session_key=self._key(client)).update(
            expire_date=timezone.now() - timedelta(seconds=1)
        )

    def test_sign_in_prunes_the_users_own_dead_records(self) -> None:
        stale = self._sign_in(self.user)
        self._expire(stale)

        self._sign_in(self.user)

        self.assertFalse(
            SessionRecord.objects.filter(session_key=self._key(stale)).exists()
        )

    def test_sign_in_leaves_other_users_recently_active_records_alone(self) -> None:
        bob_stale = self._sign_in(self._make_user("bob@example.com"))
        self._expire(bob_stale)

        self._sign_in(self.user)

        # Bob's own next sign-in or listing prunes it; Alice's does not scan it.
        self.assertTrue(
            SessionRecord.objects.filter(session_key=self._key(bob_stale)).exists()
        )

    def test_sign_in_removes_any_record_idle_longer_than_a_session_lives(self) -> None:
        bob_idle = self._sign_in(self._make_user("bob@example.com"))
        SessionRecord.objects.filter(session_key=self._key(bob_idle)).update(
            last_active_at=timezone.now()
            - timedelta(seconds=settings.SESSION_COOKIE_AGE + 1)
        )

        self._sign_in(self.user)

        self.assertFalse(
            SessionRecord.objects.filter(session_key=self._key(bob_idle)).exists()
        )

    def test_record_recreated_by_an_in_flight_request_after_revoke_is_not_listed(
        self,
    ) -> None:
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)
        desktop_key = self._key(desktop)
        desktop_id = SessionRecord.objects.get(session_key=desktop_key).id
        laptop.delete(f"{SESSIONS_URL}{desktop_id}/")

        # A desktop request that authenticated before the revoke touches late.
        SessionRecord.objects.create(
            session_key=desktop_key, user=self.user, last_active_at=timezone.now()
        )

        self.assertEqual(len(laptop.get(SESSIONS_URL).json()), 1)
        self.assertFalse(SessionRecord.objects.filter(session_key=desktop_key).exists())

    def test_sign_in_survives_a_recording_failure(self) -> None:
        with patch(
            "account_v2.session_tracking.SessionTracker._upsert",
            side_effect=RuntimeError("boom"),
        ):
            client = self._sign_in(self.user)

        self.assertIn(settings.SESSION_COOKIE_NAME, client.cookies)
        self.assertEqual(client.get(SESSIONS_URL).status_code, 200)

    def test_revoke_all_rejects_every_session(self) -> None:
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)

        response = laptop.post(REVOKE_ALL_URL)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(laptop.get(SESSIONS_URL).status_code, 401)
        self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)
        self.assertFalse(SessionRecord.objects.filter(user=self.user).exists())

    def test_revoke_all_clears_the_session_cookie(self) -> None:
        laptop = self._sign_in(self.user)

        response = laptop.post(REVOKE_ALL_URL)

        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(cookie.value, "")

    def test_revoke_all_leaves_other_users_alone(self) -> None:
        laptop = self._sign_in(self.user)
        bob = self._sign_in(self._make_user("bob@example.com"))

        laptop.post(REVOKE_ALL_URL)

        self.assertEqual(bob.get(SESSIONS_URL).status_code, 200)

    def _recording_started(self, at) -> None:
        _recording_started_at.cache_clear()
        self.addCleanup(_recording_started_at.cache_clear)
        started = patch(
            "account_v2.session_tracking._recording_started_at", return_value=at
        )
        started.start()
        self.addCleanup(started.stop)

    def test_revoke_all_ends_sessions_signed_in_before_recording(self) -> None:
        laptop = self._sign_in(self.user)
        legacy = self._sign_in(self.user)
        SessionRecord.objects.filter(session_key=self._key(legacy)).delete()
        # Recording began just after `legacy` signed in, so it expires before the
        # cutoff while every session saved since expires after it.
        self._recording_started(timezone.now() + timedelta(seconds=5))

        laptop.post(REVOKE_ALL_URL)

        self.assertFalse(Session.objects.filter(session_key=self._key(legacy)).exists())

    def test_revoke_all_skips_the_legacy_scan_once_pre_rollout_sessions_expired(
        self,
    ) -> None:
        laptop = self._sign_in(self.user)
        self._recording_started(
            timezone.now() - timedelta(seconds=settings.SESSION_COOKIE_AGE + 1)
        )

        with patch.object(Session.objects, "filter", wraps=Session.objects.filter) as q:
            SessionTracker._unrecorded_session_keys(self.user)
        q.assert_not_called()
        self.assertEqual(laptop.post(REVOKE_ALL_URL).status_code, 204)

    def test_revoke_one_leaves_the_other_working(self) -> None:
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)
        desktop_id = SessionRecord.objects.get(session_key=self._key(desktop)).id

        response = laptop.delete(f"{SESSIONS_URL}{desktop_id}/")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)
        remaining = laptop.get(SESSIONS_URL)
        self.assertEqual(remaining.status_code, 200)
        self.assertEqual(len(remaining.json()), 1)

    def test_revoking_the_current_session_signs_it_out(self) -> None:
        laptop = self._sign_in(self.user)
        laptop_id = SessionRecord.objects.get(session_key=self._key(laptop)).id

        self.assertEqual(laptop.delete(f"{SESSIONS_URL}{laptop_id}/").status_code, 204)
        self.assertEqual(laptop.get(SESSIONS_URL).status_code, 401)

    def test_another_users_session_is_not_found(self) -> None:
        laptop = self._sign_in(self.user)
        bob = self._sign_in(self._make_user("bob@example.com"))
        bob_id = SessionRecord.objects.get(session_key=self._key(bob)).id

        self.assertEqual(laptop.delete(f"{SESSIONS_URL}{bob_id}/").status_code, 404)
        self.assertEqual(laptop.delete(f"{SESSIONS_URL}not-a-uuid/").status_code, 404)
        self.assertEqual(bob.get(SESSIONS_URL).status_code, 200)

    def test_list_omits_expired_sessions_and_prunes_them(self) -> None:
        laptop = self._sign_in(self.user)
        stale = self._sign_in(self.user)
        Session.objects.filter(session_key=self._key(stale)).update(
            expire_date=timezone.now() - timedelta(seconds=1)
        )

        self.assertEqual(len(laptop.get(SESSIONS_URL).json()), 1)
        self.assertFalse(
            SessionRecord.objects.filter(session_key=self._key(stale)).exists()
        )

    def test_logout_forgets_the_session(self) -> None:
        laptop = self._sign_in(self.user)
        key = self._key(laptop)

        laptop.logout()

        self.assertFalse(SessionRecord.objects.filter(session_key=key).exists())

    def test_activity_is_refreshed_at_most_once_a_minute(self) -> None:
        laptop = self._sign_in(self.user)
        key = self._key(laptop)
        an_hour_ago = timezone.now() - timedelta(hours=1)

        laptop.get(SESSIONS_URL)  # Opens the throttle window.
        SessionRecord.objects.filter(session_key=key).update(last_active_at=an_hour_ago)
        laptop.get(SESSIONS_URL)
        self.assertEqual(
            SessionRecord.objects.get(session_key=key).last_active_at, an_hour_ago
        )

        cache.delete(f"{_TOUCH_CACHE_PREFIX}{key}")  # The window elapses.
        laptop.get(SESSIONS_URL)
        self.assertGreater(
            SessionRecord.objects.get(session_key=key).last_active_at, an_hour_ago
        )

    def test_session_from_before_recording_is_recorded_on_first_use(self) -> None:
        laptop = self._sign_in(self.user, FIREFOX_WINDOWS)
        key = self._key(laptop)
        SessionRecord.objects.filter(session_key=key).delete()

        laptop.get(SESSIONS_URL)

        record = SessionRecord.objects.get(session_key=key)
        self.assertEqual(record.user_agent, FIREFOX_WINDOWS)

    def test_location_comes_from_the_configured_resolver(self) -> None:
        _location_resolver.cache_clear()
        self.addCleanup(_location_resolver.cache_clear)
        laptop = self._sign_in(self.user)
        # `force_login` signs in without a client address; record from a real request.
        SessionRecord.objects.filter(session_key=self._key(laptop)).delete()

        with override_settings(
            SESSION_LOCATION_RESOLVER=f"{__name__}.resolve_test_location"
        ):
            response = laptop.get(SESSIONS_URL)

        self.assertEqual(response.json()[0]["location"], "near 127.0.0.1")

    def test_unauthenticated_caller_is_refused(self) -> None:
        self.assertEqual(APIClient().get(SESSIONS_URL).status_code, 401)


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=_MIDDLEWARE)
class IdentityProviderSessionTest(APITestCase):
    """Cloud plugins authenticate on `session[Z_SESSION]`, not just the user.

    The real plugins live in the cloud repo; this stand-in reproduces the part
    of their `is_authenticated` that decides whether a revoked session is
    refused, and the provider hooks a plugin may implement.
    """

    class _CloudStylePlugin:
        def __init__(self) -> None:
            self.revoked: list[str | None] = []

        def is_authenticated(self, request) -> bool:
            return request.user.is_authenticated and bool(
                request.session.get("z_session")
            )

        def list_idp_sessions(self, request) -> list[dict]:
            return [
                {
                    "id": "idp-1",
                    "browser": None,
                    "os": None,
                    "device_label": None,
                    "location": None,
                    "last_active": timezone.now(),
                    "created": timezone.now(),
                    "is_current": False,
                }
            ]

        def revoke_idp_sessions(self, request, session_id=None) -> bool:
            self.revoked.append(session_id)
            return True

    def setUp(self) -> None:
        Organization.objects.create(name=ORG, display_name="Org A", organization_id=ORG)
        self.user = User.objects.create_user(
            username="carol@example.com",
            email="carol@example.com",
            password=secrets.token_urlsafe(),
        )
        self.plugin = self._CloudStylePlugin()
        for target in (
            "account_v2.custom_auth_middleware.AuthenticationPluginRegistry",
            "account_v2.session_tracking.AuthenticationPluginRegistry",
        ):
            registry = patch(
                target,
                is_plugin_available=lambda: True,
                get_plugin=lambda: self.plugin,
            )
            registry.start()
            self.addCleanup(registry.stop)

    def _sign_in(self) -> APIClient:
        client = APIClient(HTTP_USER_AGENT=CHROME_MAC)
        client.force_login(self.user)
        session = client.session
        session["organization"] = ORG
        session["z_session"] = "token"
        session.save()
        return client

    def test_activity_is_tracked_and_provider_sessions_are_merged(self) -> None:
        laptop = self._sign_in()

        sessions = laptop.get(SESSIONS_URL).json()

        self.assertEqual([s["id"] for s in sessions][1:], ["idp-1"])
        self.assertTrue(sessions[0]["is_current"])

    def test_revoke_all_rejects_sessions_and_calls_the_provider(self) -> None:
        laptop = self._sign_in()
        desktop = self._sign_in()

        self.assertEqual(laptop.post(REVOKE_ALL_URL).status_code, 204)

        self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)
        self.assertEqual(laptop.get(SESSIONS_URL).status_code, 401)
        self.assertEqual(self.plugin.revoked, [None])

    def test_provider_failures_do_not_fail_the_request(self) -> None:
        laptop = self._sign_in()
        desktop = self._sign_in()
        broken = RuntimeError("provider down")

        with (
            patch.object(self.plugin, "list_idp_sessions", side_effect=broken),
            patch.object(self.plugin, "revoke_idp_sessions", side_effect=broken),
        ):
            self.assertEqual(len(laptop.get(SESSIONS_URL).json()), 2)
            self.assertEqual(laptop.post(REVOKE_ALL_URL).status_code, 204)

        self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)

    def test_provider_session_id_is_revoked_through_the_provider(self) -> None:
        laptop = self._sign_in()

        self.assertEqual(laptop.delete(f"{SESSIONS_URL}idp-1/").status_code, 204)
        self.assertEqual(self.plugin.revoked, ["idp-1"])


class ParseUserAgentTest(SimpleTestCase):
    def test_known_browsers_and_systems(self) -> None:
        cases = {
            CHROME_MAC: ("Chrome", "macOS"),
            FIREFOX_WINDOWS: ("Firefox", "Windows"),
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
            ): ("Edge", "Windows"),
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                "(KHTML, like Gecko) Version/18.0 Safari/605.1.15"
            ): ("Safari", "macOS"),
            (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
                "Mobile/15E148 Safari/604.1"
            ): ("Safari", "iOS"),
            (
                "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
            ): ("Chrome", "Android"),
            ("Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"): (
                "Firefox",
                "Linux",
            ),
        }
        for user_agent, (browser, os) in cases.items():
            with self.subTest(user_agent=user_agent):
                device = parse_user_agent(user_agent)
                self.assertEqual((device.browser, device.os), (browser, os))
        self.assertEqual(parse_user_agent(CHROME_MAC).label, "Chrome on macOS")

    def test_unrecognised_is_null_not_guessed(self) -> None:
        for user_agent in ("", "curl/8.4.0", "python-requests/2.32"):
            with self.subTest(user_agent=user_agent):
                device = parse_user_agent(user_agent)
                self.assertIsNone(device.browser)
                self.assertIsNone(device.os)
                self.assertIsNone(device.label)


class TouchIgnoresNonSessionRequestsTest(SimpleTestCase):
    def test_no_session_key_or_anonymous_user_is_skipped(self) -> None:
        for request in (
            SimpleNamespace(
                session=SimpleNamespace(session_key=None),
                user=SimpleNamespace(is_authenticated=True),
            ),
            SimpleNamespace(
                session=SimpleNamespace(session_key="abc"),
                user=SimpleNamespace(is_authenticated=False),
            ),
        ):
            with patch("account_v2.session_tracking.django_cache") as fake_cache:
                SessionTracker.touch(request)
            fake_cache.add.assert_not_called()


class BrowserSessionGuardTest(SimpleTestCase):
    def test_platform_key_and_sessionless_callers_are_refused(self) -> None:
        for request in (
            SimpleNamespace(
                platform_api_key=object(), session=SimpleNamespace(session_key="abc")
            ),
            SimpleNamespace(session=SimpleNamespace(session_key=None)),
        ):
            with self.assertRaises(PermissionDenied):
                _require_browser_session(request)
        _require_browser_session(
            SimpleNamespace(session=SimpleNamespace(session_key="abc"))
        )
