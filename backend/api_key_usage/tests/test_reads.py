"""Usage on the key lists, the history and callers endpoints, and the summary."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_redis import get_redis_connection
from global_api_deployment_key.models import GlobalApiDeploymentKey
from global_api_deployment_key.views import GlobalApiDeploymentKeyViewSet
from platform_api.models import PlatformApiKey
from platform_api.views import PlatformApiKeyViewSet
from platform_audit.tests.base import AuditTestBase

from api_key_usage import reads, recorder, registry
from api_key_usage.constants import FLUSH_DUE_KEY, FLUSH_LOCK_KEY, PENDING_HASHES
from api_key_usage.models import ApiKeyLastUsed, ApiKeyUsageDaily
from api_key_usage.reads import usage_status
from api_key_usage.recorder import record_key_use
from api_key_usage.registry import register_key_type
from api_key_usage.views import KeyUsageSummaryView

PLATFORM = "platform_api_key"
GLOBAL = "global_api_deployment_key"
NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


class _Key:
    def __init__(self, expires_at=None) -> None:
        self.expires_at = expires_at


class UsageStatusTests(TestCase):
    def status(self, expires_at=None, last_used_at=None) -> str:
        return usage_status(_Key(expires_at), last_used_at, NOW)

    def test_a_used_key_without_expiry_is_active(self) -> None:
        self.assertEqual(self.status(last_used_at=NOW - timedelta(days=1)), "active")

    def test_a_key_never_used_is_never_used(self) -> None:
        self.assertEqual(self.status(), "never_used")

    def test_a_key_unused_for_over_90_days_is_idle(self) -> None:
        self.assertEqual(self.status(last_used_at=NOW - timedelta(days=91)), "idle")
        self.assertEqual(self.status(last_used_at=NOW - timedelta(days=89)), "active")

    def test_a_key_expiring_within_7_days_is_expiring_even_if_unused(self) -> None:
        self.assertEqual(self.status(expires_at=NOW + timedelta(days=7)), "expiring")
        self.assertEqual(
            self.status(expires_at=NOW + timedelta(days=8)), "never_used"
        )

    def test_expired_wins_over_everything(self) -> None:
        self.assertEqual(
            self.status(expires_at=NOW, last_used_at=NOW - timedelta(days=200)),
            "expired",
        )


class ReadTestBase(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        redis = get_redis_connection("default")
        clear = lambda: redis.delete(*PENDING_HASHES, FLUSH_DUE_KEY, FLUSH_LOCK_KEY)  # noqa: E731
        clear()
        self.addCleanup(clear)
        patcher = mock.patch.object(recorder, "start_background_flush")
        patcher.start()
        self.addCleanup(patcher.stop)

    def record(self, key, key_type, at=None, **kwargs) -> None:
        record_key_use(
            key_type=key_type,
            key_id=key.id,
            organization_id=key.organization_id,
            at=at or timezone.now(),
            **kwargs,
        )


class PlatformKeyUsageTests(ReadTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.key = PlatformApiKey.objects.create(
            name="ci", description="d", organization=self.org
        )

    def test_the_list_shows_pending_usage_without_waiting_for_a_flush(self) -> None:
        self.record(self.key, PLATFORM)
        self.record(self.key, PLATFORM)
        view = PlatformApiKeyViewSet.as_view({"get": "list"})

        response = self.call(view, "get")

        row = response.data[0]
        self.assertEqual(row["calls_30d"], 2)
        self.assertEqual(row["usage_status"], "active")
        self.assertIsNotNone(row["last_used_at"])

    def test_a_key_never_used_lists_as_never_used(self) -> None:
        view = PlatformApiKeyViewSet.as_view({"get": "list"})

        row = self.call(view, "get").data[0]

        self.assertEqual(
            (row["calls_30d"], row["usage_status"], row["last_used_at"]),
            (0, "never_used", None),
        )

    def test_the_list_costs_the_same_queries_for_more_keys(self) -> None:
        view = PlatformApiKeyViewSet.as_view({"get": "list"})
        self.call(view, "get")  # warm caches

        with CaptureQueriesContext(connection) as one:
            self.call(view, "get")
        for n in range(3):
            PlatformApiKey.objects.create(
                name=f"k{n}", description="d", organization=self.org
            )
        with CaptureQueriesContext(connection) as four:
            self.call(view, "get")

        self.assertEqual(len(one), len(four))

    def test_history_is_30_zero_filled_days_ending_today(self) -> None:
        today = timezone.now()
        self.record(self.key, PLATFORM, at=today)
        self.record(self.key, PLATFORM, at=today - timedelta(days=2))
        self.record(self.key, PLATFORM, at=today - timedelta(days=2))
        view = PlatformApiKeyViewSet.as_view({"get": "history"})

        data = self.call(view, "get", pk=self.key.pk).data

        days = data["days"]
        self.assertEqual(len(days), 30)
        self.assertEqual(days[-1], {"day": today.date().isoformat(), "calls": 1})
        self.assertEqual(days[-3]["calls"], 2)
        self.assertEqual(sum(d["calls"] for d in days), 3)
        self.assertEqual(data["total_calls"], 3)
        self.assertEqual(data["usage_status"], "active")

    def test_history_of_another_orgs_key_is_not_found(self) -> None:
        other = PlatformApiKey.objects.create(
            name="x", description="d", organization=self.other_org
        )
        view = PlatformApiKeyViewSet.as_view({"get": "history"})

        self.assertEqual(self.call(view, "get", pk=other.pk).status_code, 404)

    def test_history_is_admin_only(self) -> None:
        view = PlatformApiKeyViewSet.as_view({"get": "history"})

        response = self.call(view, "get", user=self.member, pk=self.key.pk)

        self.assertEqual(response.status_code, 403)


class GlobalKeyUsageTests(ReadTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.key = GlobalApiDeploymentKey.objects.create(
            name="g", description="d", organization=self.org, allow_all_deployments=True
        )

    def test_callers_list_each_deployment_with_its_calls(self) -> None:
        busy, quiet, gone = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        for deployment, calls in ((busy, 3), (quiet, 1), (gone, 2)):
            for _ in range(calls):
                self.record(self.key, GLOBAL, api_deployment_id=deployment)
        names = {busy: ("Invoices", "invoices"), quiet: ("Receipts", "receipts")}
        found = [
            mock.Mock(id=pk, display_name=d, api_name=a) for pk, (d, a) in names.items()
        ]
        view = GlobalApiDeploymentKeyViewSet.as_view({"get": "callers"})

        with mock.patch.object(reads.APIDeployment.objects, "filter", return_value=found):
            data = self.call(view, "get", pk=self.key.pk).data

        self.assertEqual(
            [(row["api_deployment_id"], row["calls"]) for row in data],
            [(str(busy), 3), (str(gone), 2), (str(quiet), 1)],
        )
        self.assertEqual(data[0]["display_name"], "Invoices")
        self.assertIsNone(data[1]["display_name"])  # deleted since
        self.assertIsNotNone(data[0]["last_call_at"])

    def test_history_counts_the_global_key(self) -> None:
        self.record(self.key, GLOBAL, api_deployment_id=uuid.uuid4())
        view = GlobalApiDeploymentKeyViewSet.as_view({"get": "history"})

        data = self.call(view, "get", pk=self.key.pk).data

        self.assertEqual(data["total_calls"], 1)

    def test_the_list_shows_usage(self) -> None:
        self.record(self.key, GLOBAL, api_deployment_id=uuid.uuid4())
        view = GlobalApiDeploymentKeyViewSet.as_view({"get": "list"})

        row = self.call(view, "get").data[0]

        self.assertEqual((row["calls_30d"], row["usage_status"]), (1, "active"))

    def test_a_member_cannot_see_usage_of_a_key_they_did_not_create(self) -> None:
        self.org.restrict_api_key_management = False
        self.org.save()
        for action in ("history", "callers"):
            view = GlobalApiDeploymentKeyViewSet.as_view({"get": action})

            response = self.call(view, "get", user=self.member, pk=self.key.pk)

            self.assertEqual(response.status_code, 403, action)


class SummaryTests(ReadTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.view = KeyUsageSummaryView.as_view()

    def platform_key(self, **kwargs) -> PlatformApiKey:
        return PlatformApiKey.objects.create(
            name=f"p-{uuid.uuid4().hex[:6]}", description="d", organization=self.org,
            **kwargs,
        )

    def test_counts_active_keys_by_status_across_types(self) -> None:
        self.platform_key()  # never used
        self.platform_key(is_active=False)  # inactive: not counted
        expiring = self.platform_key(expires_at=timezone.now() + timedelta(days=3))
        self.record(expiring, PLATFORM)
        idle = self.platform_key()
        ApiKeyLastUsed.objects.create(
            organization=self.org, key_type=PLATFORM, key_id=idle.id,
            last_used_at=timezone.now() - timedelta(days=120),
        )
        used = GlobalApiDeploymentKey.objects.create(
            name="g", description="d", organization=self.org, allow_all_deployments=True
        )
        self.record(used, GLOBAL)
        GlobalApiDeploymentKey.objects.create(
            name="g2", description="d", organization=self.org, allow_all_deployments=True
        )  # never used

        data = self.call(self.view, "get").data

        self.assertEqual(
            (data["never_used"], data["expiring_7d"], data["idle_90d"]), (2, 1, 1)
        )
        self.assertEqual(
            data["by_type"][PLATFORM],
            {"never_used": 1, "expiring_7d": 1, "idle_90d": 1},
        )
        self.assertEqual(
            data["by_type"][GLOBAL],
            {"never_used": 1, "expiring_7d": 0, "idle_90d": 0},
        )

    def test_ignores_other_organisations(self) -> None:
        PlatformApiKey.objects.create(
            name="x", description="d", organization=self.other_org
        )

        data = self.call(self.view, "get").data

        self.assertEqual(data["never_used"], 0)

    def test_a_registered_key_type_is_counted(self) -> None:
        register_key_type(
            "test_key", lambda org: PlatformApiKey.objects.filter(organization=org)
        )
        self.addCleanup(registry._KEY_TYPES.pop, "test_key")
        self.platform_key()

        data = self.call(self.view, "get").data

        self.assertEqual(data["by_type"]["test_key"]["never_used"], 1)

    def test_is_admin_only(self) -> None:
        response = self.call(self.view, "get", user=self.member)

        self.assertEqual(response.status_code, 403)

    def test_old_daily_rows_do_not_count_toward_calls_30d(self) -> None:
        key = self.platform_key()
        ApiKeyUsageDaily.objects.create(
            organization=self.org, key_type=PLATFORM, key_id=key.id,
            day=timezone.now().date() - timedelta(days=30), calls=9,
        )

        usage = reads.usage_by_key(PLATFORM, [key])[key.id]

        self.assertEqual(usage.calls_30d, 0)
