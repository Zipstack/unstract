from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from platform_audit.models import PlatformAuditEvent
from platform_audit.tests.base import AuditTestBase


class PurgeCommandTests(AuditTestBase):
    def setUp(self) -> None:
        super().setUp()
        now = timezone.now()
        for org, days in ((self.org, 1), (self.org, 100), (self.other_org, 200)):
            PlatformAuditEvent.objects.create(
                organization=org,
                occurred_at=now - timedelta(days=days),
                actor_type="system",
                action="group.created",
                target_type="group",
            )

    def _run(self, *args) -> str:
        out = StringIO()
        call_command("purge_platform_audit_events", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_deletes_nothing(self) -> None:
        self.assertIn("would delete 2", self._run("--dry-run"))
        self.assertEqual(PlatformAuditEvent.objects.count(), 3)

    def test_deletes_only_expired_events_in_batches(self) -> None:
        self.assertIn("deleted 2", self._run("--batch-size", "1"))
        self.assertEqual(PlatformAuditEvent.objects.count(), 1)
