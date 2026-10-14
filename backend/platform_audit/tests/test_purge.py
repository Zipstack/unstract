from datetime import timedelta
from io import StringIO

from configuration.enums import ConfigKey
from configuration.models import Configuration
from django.core.management import call_command
from django.core.management.base import CommandError
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

    def test_each_organisation_uses_its_own_retention(self) -> None:
        # other_org keeps a year: its 200-day event survives the 90-day default.
        self._override(self.other_org, "365")
        # org keeps 50 days: a 60-day event the default would keep is deleted.
        self._override(self.org, "50")
        PlatformAuditEvent.objects.create(
            organization=self.org,
            occurred_at=timezone.now() - timedelta(days=60),
            actor_type="system",
            action="group.created",
            target_type="group",
        )
        self._run()
        remaining = sorted(
            (e.organization_id == self.org.id, round(self._age(e)))
            for e in PlatformAuditEvent.objects.all()
        )
        self.assertEqual(remaining, [(False, 200), (True, 1)])

    def test_bad_batch_size_is_an_error(self) -> None:
        with self.assertRaises(CommandError):
            self._run("--batch-size", "0")

    @staticmethod
    def _override(org, days: str) -> None:
        Configuration.objects.create(
            organization=org, key=ConfigKey.PLATFORM_AUDIT_RETENTION_DAYS.name, value=days
        )

    @staticmethod
    def _age(event) -> float:
        return (timezone.now() - event.occurred_at).total_seconds() / 86400
