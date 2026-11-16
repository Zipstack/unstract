"""``org_switch_via_login`` on the session response (GET /api/v1/session).

An auth plugin whose identity provider picks the organization at login sets the
session key; the SPA then changes organization by logging in again. Any other
session's response must keep exactly the fields it had, with no new key.

DB-backed Django ``TestCase`` → auto-marked ``integration`` by ``backend/conftest.py``.
"""

import secrets

from django.test import TestCase
from utils.tests.auth_seam import builtin_auth_service
from utils.user_session import UserSessionUtils

from account_v2.models import User

SESSION_URL = "/api/v1/session"
KEY = UserSessionUtils.ORG_SWITCH_VIA_LOGIN


class SessionOrgSwitchViaLoginTests(TestCase):
    def setUp(self) -> None:
        # The built-in session auth: a plugin's middleware would 401 a session
        # it did not seed.
        self.enterContext(builtin_auth_service())
        user = User.objects.create_user(
            username="switch@example.com",
            email="switch@example.com",
            password=secrets.token_urlsafe(),
        )
        self.client.force_login(user)

    def _session(self, value: object = None) -> dict:
        if value is not None:
            session = self.client.session
            session[KEY] = value
            session.save()
        response = self.client.get(SESSION_URL)
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_key_is_absent_when_no_plugin_set_it(self) -> None:
        self.assertNotIn(KEY, self._session())

    def test_key_is_true_when_a_plugin_set_it(self) -> None:
        self.assertIs(self._session(True)[KEY], True)

    def test_only_a_true_value_counts(self) -> None:
        for value in ("true", 1, False):
            with self.subTest(value=value):
                self.assertNotIn(KEY, self._session(value))
