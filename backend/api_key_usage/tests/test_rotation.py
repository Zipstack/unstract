"""Rotating a key with a grace period for its old secret, on both key types."""

import secrets
import uuid
from datetime import timedelta
from unittest import mock

from account_v2.models import User
from api_v2.exceptions import UnauthorizedKey
from api_v2.key_helper import KeyHelper
from api_v2.models import APIDeployment
from django.test import override_settings
from django.utils import timezone
from global_api_deployment_key.models import GlobalApiDeploymentKey
from global_api_deployment_key.views import GlobalApiDeploymentKeyViewSet
from platform_api.models import PlatformApiKey
from platform_api.tests.test_platform_key_middleware import _MIDDLEWARE, ECHO_URL
from platform_api.views import PlatformApiKeyViewSet
from platform_audit.tests.base import AuditTestBase

from api_key_usage import recorder
from api_key_usage.rotation import rotate_secret


class RotateSecretTests(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.key = PlatformApiKey.objects.create(
            name="ci", description="d", organization=self.org
        )

    def test_a_grace_period_keeps_the_old_secret_until_it_ends(self) -> None:
        old, now = self.key.key, timezone.now()

        rotate_secret(self.key, "24h", now=now)

        self.assertNotEqual(self.key.key, old)
        self.assertEqual(self.key.previous_key, old)
        self.assertEqual(self.key.previous_key_expires_at, now + timedelta(hours=24))

    def test_no_grace_drops_every_old_secret(self) -> None:
        rotate_secret(self.key, "7d")

        rotate_secret(self.key, "none")

        self.assertIsNone(self.key.previous_key)
        self.assertIsNone(self.key.previous_key_expires_at)

    def test_rotating_again_keeps_only_the_latest_old_secret(self) -> None:
        first = self.key.key
        rotate_secret(self.key, "7d")
        second = self.key.key

        rotate_secret(self.key, "1h")

        self.assertEqual(self.key.previous_key, second)
        self.assertNotIn(first, (self.key.key, self.key.previous_key))


@override_settings(
    ROOT_URLCONF="platform_api.tests.test_platform_key_middleware",
    MIDDLEWARE=_MIDDLEWARE,
)
class PlatformKeyRotateTests(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(recorder, "record_key_use")
        patcher.start()
        self.addCleanup(patcher.stop)
        email = "svc-ci@example.com"
        api_user = User.objects.create_user(
            username=email, email=email, password=secrets.token_urlsafe()
        )
        self.key = PlatformApiKey.objects.create(
            name="ci", description="d", organization=self.org, api_user=api_user
        )
        self.rotate = PlatformApiKeyViewSet.as_view({"post": "rotate"})

    def authenticates(self, secret) -> bool:
        response = self.client.get(ECHO_URL, HTTP_AUTHORIZATION=f"Bearer {secret}")
        return response.status_code == 200

    def test_the_old_secret_works_during_the_grace_period(self) -> None:
        old = self.key.key

        response = self.call(self.rotate, "post", data={"grace": "24h"}, pk=self.key.pk)

        self.assertEqual(response.status_code, 200, response.data)
        self.key.refresh_from_db()
        self.assertTrue(self.authenticates(old))
        self.assertTrue(self.authenticates(self.key.key))
        self.assertIsNotNone(response.data["previous_key_expires_at"])

    def test_the_old_secret_stops_working_when_the_grace_period_ends(self) -> None:
        old = self.key.key
        self.call(self.rotate, "post", data={"grace": "1h"}, pk=self.key.pk)
        PlatformApiKey.objects.filter(pk=self.key.pk).update(
            previous_key_expires_at=timezone.now() - timedelta(seconds=1)
        )

        with self.assertLogs("account_v2.custom_auth_middleware", "WARNING"):
            self.assertFalse(self.authenticates(old))

    def test_rotating_without_grace_cuts_the_old_secret_at_once(self) -> None:
        old = self.key.key

        response = self.call(self.rotate, "post", pk=self.key.pk)

        self.assertEqual(response.status_code, 200, response.data)
        with self.assertLogs("account_v2.custom_auth_middleware", "WARNING"):
            self.assertFalse(self.authenticates(old))
        self.assertEqual(self.only_event(action="key.rotated").summary, "")

    def test_an_unknown_grace_is_refused_and_changes_nothing(self) -> None:
        old = self.key.key

        response = self.call(self.rotate, "post", data={"grace": "30d"}, pk=self.key.pk)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["errors"][0]["attr"], "grace")
        self.key.refresh_from_db()
        self.assertEqual(self.key.key, old)
        self.assertFalse(self.events(action="key.rotated"))

    def test_the_rotation_audit_says_how_long_the_old_secret_works(self) -> None:
        self.call(self.rotate, "post", data={"grace": "7d"}, pk=self.key.pk)

        self.key.refresh_from_db()
        event = self.only_event(action="key.rotated")
        self.assertIn(self.key.previous_key_expires_at.isoformat(), event.summary)
        self.assertNotIn(str(self.key.previous_key), event.summary)

    def test_a_deactivated_key_rejects_its_old_secret_too(self) -> None:
        old = self.key.key
        self.call(self.rotate, "post", data={"grace": "24h"}, pk=self.key.pk)
        PlatformApiKey.objects.filter(pk=self.key.pk).update(is_active=False)

        with self.assertLogs("account_v2.custom_auth_middleware", "WARNING"):
            self.assertFalse(self.authenticates(old))


class GlobalKeyRotateTests(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.key = GlobalApiDeploymentKey.objects.create(
            name="g", description="d", organization=self.org, allow_all_deployments=True
        )
        self.deployment = APIDeployment(api_name="invoices", is_active=True)
        self.deployment.id = uuid.uuid4()
        self.deployment.organization_id = self.org.pk
        self.rotate = GlobalApiDeploymentKeyViewSet.as_view({"post": "rotate"})

    def validate(self, secret):
        return KeyHelper.validate_global_api_deployment_key(
            api_key=str(secret), api_deployment=self.deployment
        )

    def test_the_old_secret_works_during_the_grace_period(self) -> None:
        old = self.key.key

        response = self.call(self.rotate, "post", data={"grace": "1h"}, pk=self.key.pk)

        self.assertEqual(response.status_code, 200, response.data)
        self.key.refresh_from_db()
        self.assertEqual(self.validate(old), self.key)
        self.assertEqual(self.validate(self.key.key), self.key)

    def test_the_old_secret_is_refused_after_the_grace_period(self) -> None:
        old = self.key.key
        self.call(self.rotate, "post", data={"grace": "1h"}, pk=self.key.pk)
        GlobalApiDeploymentKey.objects.filter(pk=self.key.pk).update(
            previous_key_expires_at=timezone.now() - timedelta(seconds=1)
        )

        with (
            self.assertRaises(UnauthorizedKey),
            self.assertLogs("api_v2.key_helper", "WARNING"),
        ):
            self.validate(old)

    def test_rotating_without_grace_refuses_the_old_secret(self) -> None:
        old = self.key.key

        self.call(self.rotate, "post", pk=self.key.pk)

        with (
            self.assertRaises(UnauthorizedKey),
            self.assertLogs("api_v2.key_helper", "WARNING"),
        ):
            self.validate(old)

    def test_an_unknown_grace_is_refused(self) -> None:
        response = self.call(self.rotate, "post", data={"grace": "2h"}, pk=self.key.pk)

        self.assertEqual(response.status_code, 400)
