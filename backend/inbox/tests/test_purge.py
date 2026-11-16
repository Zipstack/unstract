"""Items older than 90 days are deleted by a daily periodic task."""

import importlib
from datetime import timedelta
from unittest.mock import patch

from account_v2.models import Organization
from django.apps import apps
from django.test import TestCase
from django.utils import timezone
from permissions.tests.base import CoOwnerOrgTestMixin
from pg_queue.models import PgPeriodicTask
from rest_framework.test import APIRequestFactory
from utils.user_context import UserContext

from inbox.internal_views import PurgeInboxAPIView
from inbox.models import InboxItem

seed = importlib.import_module("inbox.migrations.0002_pg_periodic_task")


class PurgeTests(CoOwnerOrgTestMixin, TestCase):
    def setUp(self) -> None:
        self._seed_org()
        self.other = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )

    def item(self, org, age_days: int, key: str) -> InboxItem:
        item = InboxItem.objects.create(
            organization=org, user=self.viewer, kind="x", title="x", dedupe_key=key
        )
        InboxItem._base_manager.filter(pk=item.pk).update(
            created_at=timezone.now() - timedelta(days=age_days)
        )
        return item

    def test_deletes_items_older_than_90_days_in_every_organization(self) -> None:
        self.item(self.org, 91, "a")
        self.item(self.other, 91, "b")
        kept = self.item(self.org, 89, "c")
        UserContext.set_organization_identifier(None)
        response = PurgeInboxAPIView.as_view()(APIRequestFactory().post("/x/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"deleted": 2})
        self.assertEqual(list(InboxItem._base_manager.all()), [kept])

    def test_deletes_in_batches(self) -> None:
        for i in range(5):
            self.item(self.org, 100, f"old{i}")
        with patch("inbox.internal_views.PURGE_BATCH", 2):
            response = PurgeInboxAPIView.as_view()(APIRequestFactory().post("/x/"))
        self.assertEqual(response.data, {"deleted": 5})
        self.assertFalse(InboxItem._base_manager.exists())

    def test_created_at_is_indexed_for_the_purge(self) -> None:
        indexed = [tuple(i.fields) for i in InboxItem._meta.indexes]
        self.assertIn(("created_at",), indexed)

    def test_schedule_row_is_seeded_inert_and_daily(self) -> None:
        seed.create_pg_periodic_task(apps, None)
        row = PgPeriodicTask.objects.get(name="inbox_purge")
        self.assertEqual(row.task_name, "inbox.purge")
        self.assertEqual(row.queue, "scheduler")
        self.assertEqual(row.cron_string, "30 2 * * *")
        self.assertFalse(row.pg_owned)
        seed.remove_pg_periodic_task(apps, None)
        self.assertFalse(PgPeriodicTask.objects.filter(name="inbox_purge").exists())
