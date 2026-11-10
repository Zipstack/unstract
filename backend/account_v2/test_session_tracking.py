"""Signed-in sessions: recording, listing and revoking through the real chain.

Revocation only means something if the next request on the revoked session is
refused, which `CustomAuthMiddleware` decides before any view runs, so these
tests drive two independent clients through a trimmed production middleware
chain rather than calling the views directly.
"""

import contextlib
import secrets
import uuid
from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.cache import cache, caches
from django.db import connection, transaction
from django.db.models.signals import post_save
from django.test import SimpleTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import include, path
from django.utils import timezone
from django.utils.crypto import salted_hmac
from platform_api.models import ApiKeyPermission, PlatformApiKey
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APITestCase
from utils import log_events

from account_v2.models import Organization, SessionRecord, User
from account_v2.session_tracking import (
    SessionTracker,
    _location_resolver,
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


def _fail_a_query(*args, **kwargs) -> None:
    """Raise a real database error, the kind that breaks an open transaction."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM no_such_table_for_this_test")


def resolve_test_location(ip_address: str) -> str:
    return f"near {ip_address}"


def resolve_long_location(ip_address: str) -> str:
    return "x" * 1000


def _isolate_side_effects(test) -> None:
    """Keep socket broadcasts out of the tests, and the shared cache clean."""
    sockets = patch("account_v2.session_tracking._disconnect_session_sockets")
    test.disconnected_sessions = sockets.start()
    test.addCleanup(sockets.stop)
    renew = patch("account_v2.session_tracking._renew_session_sockets")
    test.renewed_sessions = renew.start()
    test.addCleanup(renew.stop)
    room = patch("account_v2.session_tracking._close_socket_room")
    test.closed_rooms = room.start()
    test.addCleanup(room.stop)
    # Per-test cache keys: test workers run in parallel against one cache, so a
    # shared key would let one test's gate or cleanup decide another's outcome.
    unique = uuid.uuid4().hex
    test.sweep_key = f"session_record_idle_sweep:test:{unique}"
    test.touch_prefix = f"session_record_touch:test:{unique}:"
    for name, value in (
        ("_IDLE_SWEEP_CACHE_KEY", test.sweep_key),
        ("_TOUCH_CACHE_PREFIX", test.touch_prefix),
    ):
        key_patch = patch(f"account_v2.session_tracking.{name}", value)
        key_patch.start()
        test.addCleanup(key_patch.stop)
    test.addCleanup(cache.delete, test.sweep_key)
    if hasattr(cache, "delete_pattern"):
        test.addCleanup(cache.delete_pattern, f"{test.touch_prefix}*")


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=_MIDDLEWARE)
class SessionEndpointsTest(APITestCase):
    def setUp(self) -> None:
        Organization.objects.create(name=ORG, display_name="Org A", organization_id=ORG)
        self.user = self._make_user("alice@example.com")
        _isolate_side_effects(self)
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

        cache.delete(self.sweep_key)

        self._sign_in(self.user)

        self.assertFalse(
            SessionRecord.objects.filter(session_key=self._key(bob_idle)).exists()
        )

    def test_sign_in_sweeps_at_most_once_an_hour(self) -> None:
        cache.set(self.sweep_key, True, timeout=3600)

        with patch("account_v2.session_tracking.SessionTracker._sweep_idle") as sweep:
            self._sign_in(self.user)

        sweep.assert_not_called()

    def test_failing_sweep_does_not_lose_the_sign_in_record(self) -> None:
        # A real database error, which breaks an enclosing transaction (the test
        # case's, as ATOMIC_REQUESTS would wrap sign-in) unless it is isolated.
        cache.delete(self.sweep_key)

        with patch(
            "account_v2.session_tracking.SessionTracker._sweep_idle",
            side_effect=_fail_a_query,
        ):
            client = self._sign_in(self.user)

        self.assertTrue(
            SessionRecord.objects.filter(session_key=self._key(client)).exists()
        )

    def test_activity_sweeps_idle_records_without_any_sign_in(self) -> None:
        laptop = self._sign_in(self.user)
        bob_idle = self._sign_in(self._make_user("bob@example.com"))
        SessionRecord.objects.filter(session_key=self._key(bob_idle)).update(
            last_active_at=timezone.now()
            - timedelta(seconds=settings.SESSION_COOKIE_AGE + 1)
        )
        cache.delete(self.sweep_key)

        laptop.get(SESSIONS_URL)

        self.assertFalse(
            SessionRecord.objects.filter(session_key=self._key(bob_idle)).exists()
        )

    def test_activity_sweeps_at_most_once_an_hour(self) -> None:
        laptop = self._sign_in(self.user)
        cache.set(self.sweep_key, True, timeout=3600)
        cache.delete(f"{self.touch_prefix}{self._key(laptop)}")

        with patch("account_v2.session_tracking.SessionTracker._sweep_idle") as sweep:
            laptop.get(SESSIONS_URL)

        sweep.assert_not_called()

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

    def test_revoke_all_ends_a_session_whose_recording_failed_at_sign_in(
        self,
    ) -> None:
        laptop = self._sign_in(self.user)
        with patch(
            "account_v2.session_tracking.SessionTracker._upsert",
            side_effect=RuntimeError("boom"),
        ):
            unrecorded = self._sign_in(self.user)
        self.assertFalse(
            SessionRecord.objects.filter(session_key=self._key(unrecorded)).exists()
        )

        # No request from the unrecorded browser in between, so nothing lazily
        # records it before the revoke.
        laptop.post(REVOKE_ALL_URL)

        self.assertEqual(unrecorded.get(SESSIONS_URL).status_code, 401)

    def test_revoke_all_ends_sessions_signed_in_before_recording(self) -> None:
        laptop = self._sign_in(self.user)
        legacy = self._sign_in(self.user)
        SessionRecord.objects.filter(session_key=self._key(legacy)).delete()

        laptop.post(REVOKE_ALL_URL)

        self.assertEqual(legacy.get(SESSIONS_URL).status_code, 401)

    def test_signing_in_again_after_revoke_all_works(self) -> None:
        laptop = self._sign_in(self.user)
        laptop.post(REVOKE_ALL_URL)

        # The auth flows load the user fresh, with the bumped generation.
        self.user.refresh_from_db()
        again = self._sign_in(self.user)

        self.assertEqual(again.get(SESSIONS_URL).status_code, 200)

    def test_full_save_of_a_user_loaded_before_revoke_all_keeps_it_revoked(
        self,
    ) -> None:
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)
        # Unrecorded, so revoke-all cannot delete it: only the bumped generation
        # refuses it, which is what a stale full save would undo.
        SessionRecord.objects.filter(session_key=self._key(desktop)).delete()
        loaded_earlier = User.objects.get(pk=self.user.pk)

        laptop.post(REVOKE_ALL_URL)
        loaded_earlier.first_name = "Alice"
        loaded_earlier.save()

        self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)
        loaded_earlier.refresh_from_db()
        self.assertEqual(loaded_earlier.first_name, "Alice")
        self.assertEqual(loaded_earlier.session_generation, 1)

    def test_revoke_all_survives_a_secret_key_rotation(self) -> None:
        old_key, new_key = "a" * 50, "b" * 50
        with override_settings(SECRET_KEY=old_key):
            laptop = self._sign_in(self.user)
            laptop.post(REVOKE_ALL_URL)
            self.user.refresh_from_db()
            desktop = self._sign_in(self.user)

        with override_settings(SECRET_KEY=new_key, SECRET_KEY_FALLBACKS=[old_key]):
            self.assertEqual(desktop.get(SESSIONS_URL).status_code, 200)

    def test_sessions_from_before_the_generation_existed_stay_valid(self) -> None:
        # Generation 0 must hash exactly as Django does, or deploying this would
        # sign every user out. Computed independently of the model's override.
        stock_hash = salted_hmac(
            "django.contrib.auth.models.AbstractBaseUser.get_session_auth_hash",
            self.user.password,
            algorithm="sha256",
        ).hexdigest()

        self.assertEqual(self.user.get_session_auth_hash(), stock_hash)
        self.user.session_generation = 1
        self.assertNotEqual(self.user.get_session_auth_hash(), stock_hash)

    def test_full_save_keeps_djangos_full_save_semantics(self) -> None:
        seen = []

        def receiver(sender, update_fields, **kwargs):
            seen.append(update_fields)

        post_save.connect(receiver, sender=User)
        self.addCleanup(post_save.disconnect, receiver, sender=User)
        with CaptureQueriesContext(connection) as queries:
            self.user.save()

        self.assertEqual(seen, [None])
        (update,) = (q["sql"] for q in queries if q["sql"].startswith("UPDATE"))
        self.assertIn('"session_generation" = "user"."session_generation"', update)

    def test_full_save_of_a_partially_loaded_user_writes_only_loaded_fields(
        self,
    ) -> None:
        User.objects.filter(pk=self.user.pk).update(last_name="Original")
        partial = User.objects.only("id", "first_name").get(pk=self.user.pk)
        User.objects.filter(pk=self.user.pk).update(
            last_name="Changed meanwhile", session_generation=3
        )

        partial.first_name = "Alice"
        with CaptureQueriesContext(connection) as queries:
            partial.save()

        (update,) = (q["sql"] for q in queries if q["sql"].startswith("UPDATE"))
        self.assertNotIn('"last_name"', update)
        self.user.refresh_from_db()
        self.assertEqual(
            (self.user.first_name, self.user.last_name, self.user.session_generation),
            ("Alice", "Changed meanwhile", 3),
        )

    def test_positional_full_save_cannot_write_back_a_stale_generation(self) -> None:
        loaded_earlier = User.objects.get(pk=self.user.pk)
        User.objects.filter(pk=self.user.pk).update(session_generation=5)

        loaded_earlier.save(False, False)

        self.user.refresh_from_db()
        self.assertEqual(self.user.session_generation, 5)
        self.assertEqual(loaded_earlier.session_generation, 0)

    def test_revoke_all_completes_when_clearing_logs_fails(self) -> None:
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)

        with (
            patch(
                "account_v2.session_tracking.LogService.remove_logs_on_logout",
                side_effect=ConnectionError("redis down"),
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = laptop.post(REVOKE_ALL_URL)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME].value, "")
        self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)
        self.assertFalse(SessionRecord.objects.filter(user=self.user).exists())

    def test_revoke_one_completes_when_clearing_logs_fails(self) -> None:
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)
        desktop_id = SessionRecord.objects.get(session_key=self._key(desktop)).id

        with (
            patch(
                "account_v2.session_tracking.LogService.remove_logs_on_logout",
                side_effect=ConnectionError("redis down"),
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = laptop.delete(f"{SESSIONS_URL}{desktop_id}/")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)

    def test_revoke_all_carries_on_past_a_session_it_fails_to_end(self) -> None:
        laptop = self._sign_in(self.user)
        others = {self._key(self._sign_in(self.user)) for _ in range(2)}
        laptop_key = self._key(laptop)
        real_end = SessionTracker._end.__func__
        failed = []

        def end_failing_for_the_first(cls, request, session_key):
            # Whichever other session comes first, so the order does not matter.
            if session_key != laptop_key and not failed:
                failed.append(session_key)
                _fail_a_query()
            real_end(cls, request, session_key)

        with patch.object(SessionTracker, "_end", classmethod(end_failing_for_the_first)):
            response = laptop.post(REVOKE_ALL_URL)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME].value, "")
        (failing,) = failed
        (other,) = others - {failing}
        self.assertFalse(Session.objects.filter(session_key=other).exists())
        # Refused by the generation either way, so not left listed.
        self.assertFalse(SessionRecord.objects.filter(session_key=failing).exists())

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

        cache.delete(f"{self.touch_prefix}{key}")  # The window elapses.
        laptop.get(SESSIONS_URL)
        self.assertGreater(
            SessionRecord.objects.get(session_key=key).last_active_at, an_hour_ago
        )

    def test_activity_keeps_the_sessions_socket_tracking_alive(self) -> None:
        laptop = self._sign_in(self.user)

        laptop.get(SESSIONS_URL)

        self.renewed_sessions.assert_called_once_with(self._key(laptop))

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

    def test_unimportable_resolver_still_records_the_session(self) -> None:
        _location_resolver.cache_clear()
        self.addCleanup(_location_resolver.cache_clear)
        laptop = self._sign_in(self.user)
        SessionRecord.objects.filter(session_key=self._key(laptop)).delete()

        with override_settings(SESSION_LOCATION_RESOLVER="no_such_module.resolve"):
            response = laptop.get(SESSIONS_URL)

        self.assertEqual(len(response.json()), 1)
        self.assertIsNone(response.json()[0]["location"])

    def test_platform_key_cannot_manage_sessions(self) -> None:
        service_account = User.objects.create_user(
            username="svc@example.com",
            email="svc@example.com",
            password=secrets.token_urlsafe(),
            is_service_account=True,
        )
        key = PlatformApiKey.objects.create(
            name="key",
            description="test key",
            organization=Organization.objects.get(organization_id=ORG),
            api_user=service_account,
            permission=ApiKeyPermission.FULL_ACCESS,
        )
        browser = self._sign_in(service_account)
        record = SessionRecord.objects.get(user=service_account)
        bearer = APIClient(HTTP_AUTHORIZATION=f"Bearer {key.key}")
        # With the session cookie too, so the refusal is for the key itself.
        bearer.cookies = browser.cookies

        for method, url in (
            ("get", SESSIONS_URL),
            ("post", REVOKE_ALL_URL),
            ("delete", f"{SESSIONS_URL}{record.id}/"),
        ):
            with self.subTest(method=method):
                self.assertEqual(getattr(bearer, method)(url).status_code, 403)
        service_account.refresh_from_db()
        self.assertEqual(service_account.session_generation, 0)
        self.assertTrue(SessionRecord.objects.filter(id=record.id).exists())

    def test_a_failing_activity_refresh_does_not_fail_the_request(self) -> None:
        laptop = self._sign_in(self.user)
        cache.delete(f"{self.touch_prefix}{self._key(laptop)}")

        with patch(
            "account_v2.session_tracking.django_cache.add",
            side_effect=ConnectionError("redis down"),
        ):
            self.assertEqual(laptop.get(SESSIONS_URL).status_code, 200)

    def test_a_database_error_in_the_activity_refresh_is_contained(self) -> None:
        # Inside the test case's transaction, as ATOMIC_REQUESTS would wrap it: a
        # real database error must not leave that transaction unusable.
        laptop = self._sign_in(self.user)

        with patch(
            "django.db.models.query.QuerySet.update",
            side_effect=_fail_a_query,
        ):
            self.assertEqual(laptop.get(SESSIONS_URL).status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_revoke_all_survives_a_database_error_ending_the_current_session(
        self,
    ) -> None:
        # Under ATOMIC_REQUESTS a swallowed database error outside a savepoint
        # would roll back the bump and every deletion behind a 204.
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)
        laptop_key = self._key(laptop)
        db_store = import_module("django.contrib.sessions.backends.db").SessionStore
        real_delete = db_store.delete

        def delete_failing_for_the_current(store, session_key=None):
            if (session_key or store.session_key) == laptop_key:
                with transaction.atomic(savepoint=False):
                    _fail_a_query()
            real_delete(store, session_key)

        with (
            patch.dict(connection.settings_dict, {"ATOMIC_REQUESTS": True}),
            patch.object(db_store, "delete", delete_failing_for_the_current),
        ):
            response = laptop.post(REVOKE_ALL_URL)

        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.session_generation, 1)
        self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)

    def test_an_ended_session_is_refused_even_if_its_cached_copy_cannot_go(
        self,
    ) -> None:
        laptop = self._sign_in(self.user)
        Session.objects.filter(session_key=self._key(laptop)).delete()

        with self._cache_delete_fails():
            self.assertEqual(laptop.get(SESSIONS_URL).status_code, 401)

    def _cache_delete_fails(self):
        return patch.object(
            caches[settings.SESSION_CACHE_ALIAS],
            "delete",
            side_effect=ConnectionError("redis down"),
        )

    def test_a_session_re_cached_after_revoke_is_refused(self) -> None:
        # A request racing the revoke can put the cached copy back after the row
        # is gone; that copy alone must not keep the session alive.
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)
        desktop_key = self._key(desktop)
        store = import_module(settings.SESSION_ENGINE).SessionStore
        cache_key = store(session_key=desktop_key).cache_key
        session_cache = caches[settings.SESSION_CACHE_ALIAS]
        cached_copy = (
            session_cache.get(cache_key) or store(session_key=desktop_key).load()
        )
        desktop_id = SessionRecord.objects.get(session_key=desktop_key).id

        laptop.delete(f"{SESSIONS_URL}{desktop_id}/")
        session_cache.set(cache_key, cached_copy, 3600)

        self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)
        self.assertIsNone(session_cache.get(cache_key))
        self.assertEqual(len(laptop.get(SESSIONS_URL).json()), 1)

    def test_revoke_one_ends_the_session_when_its_cached_copy_cannot_go(
        self,
    ) -> None:
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)
        desktop_key = self._key(desktop)
        desktop_id = SessionRecord.objects.get(session_key=desktop_key).id

        with self._cache_delete_fails():
            response = laptop.delete(f"{SESSIONS_URL}{desktop_id}/")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)
        self.assertEqual(len(laptop.get(SESSIONS_URL).json()), 1)

    def test_a_revoked_session_whose_cached_copy_cannot_go_stays_refused(
        self,
    ) -> None:
        # The first refusal must not open the refresh window: one that did would
        # let every later replay of the cookie in that window skip the row check.
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)
        desktop_key = self._key(desktop)
        desktop_id = SessionRecord.objects.get(session_key=desktop_key).id

        with self._copy_delete_fails(desktop_key):
            laptop.delete(f"{SESSIONS_URL}{desktop_id}/")
            for attempt in range(3):
                with self.subTest(attempt=attempt):
                    # Each refusal clears the cookie; a replay sends it again.
                    desktop.cookies[settings.SESSION_COOKIE_NAME] = desktop_key
                    self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)
            cache.delete(f"{self.touch_prefix}{desktop_key}")  # A minute passes.
            desktop.cookies[settings.SESSION_COOKIE_NAME] = desktop_key
            self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)

        self.assertIsNone(cache.get(f"{self.touch_prefix}{desktop_key}"))

    def test_revoking_inside_an_open_window_refuses_the_surviving_copy(
        self,
    ) -> None:
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)
        desktop_key = self._key(desktop)
        desktop_id = SessionRecord.objects.get(session_key=desktop_key).id
        desktop.get(SESSIONS_URL)  # Opens the desktop's refresh window.
        self.assertIsNotNone(cache.get(f"{self.touch_prefix}{desktop_key}"))

        with self._copy_delete_fails(desktop_key) as copy_key:
            laptop.delete(f"{SESSIONS_URL}{desktop_id}/")

        self.assertIsNotNone(caches[settings.SESSION_CACHE_ALIAS].get(copy_key))
        self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)

    @contextlib.contextmanager
    def _copy_delete_fails(self, session_key: str):
        """Fail deleting only this session's cached copy, not other cache keys."""
        session_cache = caches[settings.SESSION_CACHE_ALIAS]
        copy_key = (
            import_module(settings.SESSION_ENGINE)
            .SessionStore(session_key=session_key)
            .cache_key
        )
        real_delete = session_cache.delete

        def delete(key, *args, **kwargs):
            if key == copy_key:
                raise ConnectionError("redis down")
            return real_delete(key, *args, **kwargs)

        with patch.object(session_cache, "delete", delete):
            yield copy_key

    def test_an_unreadable_refresh_window_still_checks_the_row(self) -> None:
        laptop = self._sign_in(self.user)
        laptop_key = self._key(laptop)
        laptop.get(SESSIONS_URL)  # Opens the throttle window.
        Session.objects.filter(session_key=laptop_key).delete()
        touch_key = f"{self.touch_prefix}{laptop_key}"
        real_get = cache.get

        def get_failing_for_the_window(key, *args, **kwargs):
            # The session's cached copy still loads; only the window is unread.
            if key == touch_key:
                raise ConnectionError("redis down")
            return real_get(key, *args, **kwargs)

        with (
            self._copy_delete_fails(laptop_key),
            patch.object(cache, "get", get_failing_for_the_window),
        ):
            self.assertEqual(laptop.get(SESSIONS_URL).status_code, 401)

    def test_a_throttled_request_does_not_query_the_session(self) -> None:
        laptop = self._sign_in(self.user)
        laptop.get(SESSIONS_URL)  # Opens the throttle window.

        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(laptop.get(SESSIONS_URL).status_code, 200)

        sql = [q["sql"] for q in queries]
        # The view itself reads django_session to list sessions; the throttled
        # touch adds neither the row check nor an activity write.
        self.assertFalse(
            [q for q in sql if 'FROM "django_session"' in q and "LIMIT 1" in q]
        )
        self.assertFalse([q for q in sql if q.startswith('UPDATE "session_record')])

    def test_revoking_the_current_session_when_its_cached_copy_cannot_go(
        self,
    ) -> None:
        laptop = self._sign_in(self.user)
        laptop_id = SessionRecord.objects.get(session_key=self._key(laptop)).id

        with self._cache_delete_fails():
            response = laptop.delete(f"{SESSIONS_URL}{laptop_id}/")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME].value, "")
        self.assertEqual(laptop.get(SESSIONS_URL).status_code, 401)

    def test_revoke_all_completes_when_the_session_cache_cannot_delete(self) -> None:
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)

        with self._cache_delete_fails():
            response = laptop.post(REVOKE_ALL_URL)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME].value, "")
        self.assertEqual(desktop.get(SESSIONS_URL).status_code, 401)

    def test_revoking_one_disconnects_only_that_sessions_sockets(self) -> None:
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)
        desktop_key = self._key(desktop)
        desktop_id = SessionRecord.objects.get(session_key=desktop_key).id

        with self.captureOnCommitCallbacks(execute=True):
            laptop.delete(f"{SESSIONS_URL}{desktop_id}/")

        self.disconnected_sessions.assert_called_once_with(desktop_key)
        # The per-user room is shared with the sessions that remain.
        self.closed_rooms.assert_not_called()

    def test_revoking_all_disconnects_every_session_and_empties_the_user_room(
        self,
    ) -> None:
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)
        keys = {self._key(laptop), self._key(desktop)}

        with self.captureOnCommitCallbacks(execute=True):
            laptop.post(REVOKE_ALL_URL)

        disconnected = {c.args[0] for c in self.disconnected_sessions.call_args_list}
        self.assertEqual(disconnected, keys)
        self.closed_rooms.assert_called_once_with(f"user:{self.user.pk}")

    def test_socket_cleanup_waits_for_the_commit(self) -> None:
        # Before the commit a reconnecting socket would still pass, and would
        # join after a cleanup that had already run.
        laptop = self._sign_in(self.user)
        self._sign_in(self.user)

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            laptop.post(REVOKE_ALL_URL)
            self.closed_rooms.assert_not_called()
            self.disconnected_sessions.assert_not_called()

        for callback in callbacks:
            callback()
        self.closed_rooms.assert_called_once_with(f"user:{self.user.pk}")
        self.assertEqual(self.disconnected_sessions.call_count, 2)

    def test_revoking_clears_the_sessions_logs(self) -> None:
        laptop = self._sign_in(self.user)
        desktop = self._sign_in(self.user)
        desktop_key = self._key(desktop)
        desktop_id = SessionRecord.objects.get(session_key=desktop_key).id

        with (
            patch(
                "account_v2.session_tracking.LogService.remove_logs_on_logout"
            ) as remove_logs,
            self.captureOnCommitCallbacks(execute=True),
        ):
            laptop.delete(f"{SESSIONS_URL}{desktop_id}/")

        remove_logs.assert_called_once_with(session_id=desktop_key)

    def test_sign_out_survives_a_failure_to_forget_the_session(self) -> None:
        laptop = self._sign_in(self.user)
        key = self._key(laptop)

        with patch(
            "account_v2.session_tracking.SessionTracker.forget",
            side_effect=RuntimeError("boom"),
        ):
            laptop.logout()

        self.assertFalse(Session.objects.filter(session_key=key).exists())

    def test_an_over_long_location_is_truncated(self) -> None:
        _location_resolver.cache_clear()
        self.addCleanup(_location_resolver.cache_clear)
        laptop = self._sign_in(self.user)
        SessionRecord.objects.filter(session_key=self._key(laptop)).delete()

        with override_settings(
            SESSION_LOCATION_RESOLVER=f"{__name__}.resolve_long_location"
        ):
            laptop.get(SESSIONS_URL)

        record = SessionRecord.objects.get(session_key=self._key(laptop))
        self.assertEqual(len(record.location), 255)

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
        _isolate_side_effects(self)
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

    def test_provider_failure_on_one_session_is_a_502_not_a_404(self) -> None:
        laptop = self._sign_in()
        # The exception logger signals 5xx responses, which the test client would
        # otherwise re-raise instead of returning the response.
        laptop.raise_request_exception = False

        with patch.object(
            self.plugin, "revoke_idp_sessions", side_effect=RuntimeError("down")
        ):
            response = laptop.delete(f"{SESSIONS_URL}idp-1/")

        self.assertEqual(response.status_code, 502)

    def test_malformed_provider_entries_are_dropped(self) -> None:
        laptop = self._sign_in()
        good = self.plugin.list_idp_sessions(None)[0]
        malformed = [
            {"id": "idp-2"},
            {**good, "id": "idp-3", "last_active": "later"},
            None,
            "not-a-session",
        ]

        with patch.object(
            self.plugin, "list_idp_sessions", return_value=[good, *malformed]
        ):
            response = laptop.get(SESSIONS_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([s["id"] for s in response.json()][1:], ["idp-1"])

    def test_provider_entries_are_never_current_and_blanks_read_as_null(
        self,
    ) -> None:
        laptop = self._sign_in()
        entry = {
            **self.plugin.list_idp_sessions(None)[0],
            "location": "",
            "is_current": True,
        }

        with patch.object(self.plugin, "list_idp_sessions", return_value=[entry]):
            sessions = laptop.get(SESSIONS_URL).json()

        provider = sessions[1]
        self.assertEqual(provider["id"], "idp-1")
        self.assertFalse(provider["is_current"])
        self.assertIsNone(provider["location"])
        self.assertEqual([s["is_current"] for s in sessions], [True, False])

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
            fake_cache.get.assert_not_called()
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


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=_MIDDLEWARE)
class SocketAfterRevokeTest(APITestCase):
    """A socket reconnecting with a revoked session must not regain the user room.

    The cached copy of a session can outlive its row (a failed cache delete, or a
    request re-caching it during a revoke), and the socket path reads that copy.
    """

    def setUp(self) -> None:
        Organization.objects.create(name=ORG, display_name="Org A", organization_id=ORG)
        self.user = User.objects.create_user(
            username="dana@example.com",
            email="dana@example.com",
            password=secrets.token_urlsafe(),
        )
        # It would close the test's own transaction, as the test client avoids.
        patcher = patch.object(log_events, "close_old_connections")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_session_whose_row_is_gone_gets_no_user_room(self) -> None:
        client = APIClient()
        client.force_login(self.user)
        key = client.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertEqual(log_events._get_user_id("sid-1", key), str(self.user.pk))

        # The row goes; the cached copy stays.
        Session.objects.filter(session_key=key).delete()

        self.assertIsNone(log_events._get_user_id("sid-1", key))
