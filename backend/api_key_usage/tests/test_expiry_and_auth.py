"""Key expiry and usage recording on both key types' auth paths."""

import secrets
import uuid
from datetime import timedelta
from unittest import mock

from account_v2.models import Organization, User
from api_v2 import deployment_helper
from api_v2.deployment_helper import DeploymentHelper
from api_v2.exceptions import ExpiredKey, UnauthorizedKey
from api_v2.key_helper import KeyHelper
from api_v2.models import APIDeployment
from django.test import override_settings
from django.utils import timezone
from django_redis import get_redis_connection
from global_api_deployment_key.models import GlobalApiDeploymentKey
from global_api_deployment_key.views import GlobalApiDeploymentKeyViewSet
from platform_api.models import PlatformApiKey
from platform_api.tests.test_platform_key_middleware import _MIDDLEWARE, ECHO_URL
from platform_api.views import PlatformApiKeyViewSet
from platform_audit.tests.base import AuditTestBase
from rest_framework.test import APITestCase

from api_key_usage import recorder
from api_key_usage.constants import FLUSH_DUE_KEY, FLUSH_LOCK_KEY, PENDING_HASHES
from api_key_usage.flush import flush_pending_usage
from api_key_usage.models import ApiKeyLastUsed, ApiKeyUsageDaily


def _clear_redis() -> None:
    get_redis_connection("default").delete(*PENDING_HASHES, FLUSH_DUE_KEY, FLUSH_LOCK_KEY)


@override_settings(
    ROOT_URLCONF="platform_api.tests.test_platform_key_middleware",
    MIDDLEWARE=_MIDDLEWARE,
)
class PlatformKeyAuthTests(APITestCase):
    def setUp(self) -> None:
        _clear_redis()
        self.addCleanup(_clear_redis)
        patcher = mock.patch.object(recorder, "start_background_flush")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        self.other_org = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )

    def make_key(self, organization=None, **kwargs) -> PlatformApiKey:
        email = f"svc-{uuid.uuid4().hex[:8]}@example.com"
        api_user = User.objects.create_user(
            username=email, email=email, password=secrets.token_urlsafe()
        )
        return PlatformApiKey.objects.create(
            name=f"key-{uuid.uuid4().hex[:8]}",
            description="test key",
            organization=organization or self.org,
            api_user=api_user,
            **kwargs,
        )

    def call(self, key: PlatformApiKey):
        return self.client.get(ECHO_URL, HTTP_AUTHORIZATION=f"Bearer {key.key}")

    def calls_recorded(self, key: PlatformApiKey) -> int:
        flush_pending_usage()
        return sum(
            ApiKeyUsageDaily.objects.filter(key_id=key.id).values_list("calls", flat=True)
        )

    def test_a_key_without_expiry_authenticates_and_is_counted(self) -> None:
        key = self.make_key()

        response = self.call(key)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls_recorded(key), 1)
        last = ApiKeyLastUsed.objects.get(key_id=key.id)
        self.assertEqual(last.key_type, "platform_api_key")
        self.assertEqual(last.organization, self.org)

    def test_a_key_before_its_expiry_authenticates(self) -> None:
        key = self.make_key(expires_at=timezone.now() + timedelta(days=1))

        self.assertEqual(self.call(key).status_code, 200)

    def test_an_expired_key_is_rejected_and_not_counted(self) -> None:
        key = self.make_key(expires_at=timezone.now() - timedelta(seconds=1))

        with self.assertLogs("account_v2.custom_auth_middleware", "WARNING") as logs:
            response = self.call(key)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"message": "API key expired"})
        self.assertIn("expired key", logs.output[0])
        self.assertEqual(self.calls_recorded(key), 0)

    def test_a_key_refused_for_another_org_is_not_counted(self) -> None:
        key = self.make_key(organization=self.other_org)

        self.assertEqual(self.call(key).status_code, 403)
        self.assertEqual(self.calls_recorded(key), 0)

    def test_a_recording_failure_does_not_fail_the_request(self) -> None:
        key = self.make_key()

        with (
            mock.patch.object(
                recorder, "get_redis_connection", side_effect=ConnectionError
            ),
            self.assertLogs(recorder.logger, "ERROR"),
        ):
            response = self.call(key)

        self.assertEqual(response.status_code, 200)


class GlobalKeyAuthTests(AuditTestBase):
    """``validate_api`` falls back to the global key when the deployment key fails."""

    def setUp(self) -> None:
        super().setUp()
        self.deployment = APIDeployment(api_name="invoices", is_active=True)
        self.deployment.id = uuid.uuid4()
        self.deployment.organization_id = self.org.pk
        no_deployment_key = mock.patch.object(
            KeyHelper, "validate_api_key", side_effect=UnauthorizedKey
        )
        no_deployment_key.start()
        self.addCleanup(no_deployment_key.stop)

    def make_key(self, **kwargs) -> GlobalApiDeploymentKey:
        return GlobalApiDeploymentKey.objects.create(
            name=f"g-{uuid.uuid4().hex[:8]}",
            description="d",
            organization=self.org,
            allow_all_deployments=True,
            **kwargs,
        )

    def validate(self, key: GlobalApiDeploymentKey):
        with mock.patch.object(deployment_helper, "record_key_use") as record:
            result = DeploymentHelper.validate_api(self.deployment, str(key.key))
        return result, record

    def test_a_global_key_use_is_recorded_with_its_deployment(self) -> None:
        key = self.make_key()

        result, record = self.validate(key)

        self.assertEqual(result, key)
        record.assert_called_once_with(
            key_type="global_api_deployment_key",
            key_id=key.id,
            organization_id=self.org.pk,
            api_deployment_id=self.deployment.id,
        )

    def test_a_key_before_its_expiry_is_accepted(self) -> None:
        key = self.make_key(expires_at=timezone.now() + timedelta(hours=1))

        result, _ = self.validate(key)

        self.assertEqual(result, key)

    def test_an_expired_key_gets_a_401_saying_so(self) -> None:
        key = self.make_key(expires_at=timezone.now() - timedelta(seconds=1))

        with (
            self.assertRaises(ExpiredKey) as caught,
            self.assertLogs("api_v2.key_helper", "WARNING"),
        ):
            self.validate(key)

        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(str(caught.exception.detail), "API key expired")

    def test_an_expired_key_is_not_recorded(self) -> None:
        key = self.make_key(expires_at=timezone.now() - timedelta(seconds=1))

        with (
            mock.patch.object(deployment_helper, "record_key_use") as record,
            self.assertRaises(ExpiredKey),
            self.assertLogs("api_v2.key_helper", "WARNING"),
        ):
            DeploymentHelper.validate_api(self.deployment, str(key.key))

        record.assert_not_called()

    def test_an_unknown_key_still_gets_the_generic_401(self) -> None:
        with (
            self.assertRaises(UnauthorizedKey) as caught,
            self.assertLogs("api_v2.key_helper", "WARNING"),
        ):
            DeploymentHelper.validate_api(self.deployment, str(uuid.uuid4()))

        self.assertNotIsInstance(caught.exception, ExpiredKey)


class PlatformKeyExpiryEditTests(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.key = PlatformApiKey.objects.create(
            name="ci", description="d", organization=self.org
        )
        self.update = PlatformApiKeyViewSet.as_view({"patch": "partial_update"})

    def test_setting_an_expiry_saves_and_audits_it(self) -> None:
        expires = timezone.now() + timedelta(days=30)

        response = self.call(
            self.update, "patch", data={"expires_at": expires.isoformat()}, pk=self.key.pk
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.key.refresh_from_db()
        self.assertEqual(self.key.expires_at, expires)
        self.assertIsNotNone(response.data["expires_at"])
        event = self.only_event(action="key.expiry_set")
        self.assert_admin_actor(event)
        self.assertEqual(
            (event.target_type, event.target_id, event.target_name),
            ("platform_api_key", str(self.key.id), "ci"),
        )
        self.assertEqual(
            event.changes,
            {
                "before": {"expires_at": None},
                "after": {"expires_at": expires.isoformat()},
            },
        )
        # Only the expiry changed, so no key.changed alongside it.
        self.assertEqual([e.action for e in self.events()], ["key.expiry_set"])

    def test_clearing_an_expiry_is_audited(self) -> None:
        expires = timezone.now() + timedelta(days=3)
        self.key.expires_at = expires
        self.key.save()

        response = self.call(
            self.update, "patch", data={"expires_at": None}, pk=self.key.pk
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.key.refresh_from_db()
        self.assertIsNone(self.key.expires_at)
        event = self.only_event(action="key.expiry_set")
        self.assertEqual(
            event.changes,
            {
                "before": {"expires_at": expires.isoformat()},
                "after": {"expires_at": None},
            },
        )

    def test_an_edit_that_leaves_the_expiry_alone_records_no_expiry_event(self) -> None:
        self.call(self.update, "patch", data={"description": "new"}, pk=self.key.pk)

        self.assertEqual([e.action for e in self.events()], ["key.changed"])

    def test_an_expiry_in_the_past_is_refused(self) -> None:
        past = timezone.now() - timedelta(minutes=1)

        response = self.call(
            self.update, "patch", data={"expires_at": past.isoformat()}, pk=self.key.pk
        )

        self.assertEqual(response.status_code, 400)
        self.key.refresh_from_db()
        self.assertIsNone(self.key.expires_at)
        self.assertEqual(self.events(), [])

    def test_a_key_created_with_an_expiry_audits_it(self) -> None:
        create = PlatformApiKeyViewSet.as_view({"post": "create"})
        expires = timezone.now() + timedelta(days=90)

        response = self.call(
            create,
            "post",
            data={"name": "etl", "description": "x", "expires_at": expires.isoformat()},
        )

        self.assertEqual(response.status_code, 201, response.data)
        key = PlatformApiKey.objects.get(name="etl")
        self.assertEqual(key.expires_at, expires)
        self.assertEqual(
            [e.action for e in self.events()], ["key.created", "key.expiry_set"]
        )

    def test_a_key_created_without_an_expiry_never_expires(self) -> None:
        create = PlatformApiKeyViewSet.as_view({"post": "create"})

        self.call(create, "post", data={"name": "etl", "description": "x"})

        self.assertIsNone(PlatformApiKey.objects.get(name="etl").expires_at)
        self.assertEqual([e.action for e in self.events()], ["key.created"])

    def test_the_list_shows_the_expiry(self) -> None:
        expires = timezone.now() + timedelta(days=1)
        self.key.expires_at = expires
        self.key.save()
        view = PlatformApiKeyViewSet.as_view({"get": "list"})

        response = self.call(view, "get")

        self.assertEqual(response.data[0]["expires_at"], expires.isoformat().replace("+00:00", "Z"))


class GlobalKeyExpiryEditTests(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.key = GlobalApiDeploymentKey.objects.create(
            name="g", description="d", organization=self.org, allow_all_deployments=True
        )

    def test_setting_an_expiry_saves_and_audits_it(self) -> None:
        update = GlobalApiDeploymentKeyViewSet.as_view({"patch": "partial_update"})
        expires = timezone.now() + timedelta(days=7)

        response = self.call(
            update, "patch", data={"expires_at": expires.isoformat()}, pk=self.key.pk
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.key.refresh_from_db()
        self.assertEqual(self.key.expires_at, expires)
        event = self.only_event(action="key.expiry_set")
        self.assertEqual(event.target_type, "global_api_deployment_key")
        self.assertEqual(event.changes["after"], {"expires_at": expires.isoformat()})

    def test_a_key_created_with_an_expiry_audits_it(self) -> None:
        create = GlobalApiDeploymentKeyViewSet.as_view({"post": "create"})
        expires = timezone.now() + timedelta(days=1)

        response = self.call(
            create,
            "post",
            data={
                "name": "g2",
                "description": "x",
                "allow_all_deployments": True,
                "expires_at": expires.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            [e.action for e in self.events()], ["key.created", "key.expiry_set"]
        )
