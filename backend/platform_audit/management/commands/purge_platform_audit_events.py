"""Delete platform audit events older than each organisation's retention.

Reads already hide expired events, so running this reclaims space and makes a
lowered retention final. Run it regularly::

    python manage.py purge_platform_audit_events --dry-run
    python manage.py purge_platform_audit_events --batch-size 5000
"""

from datetime import timedelta

from account_v2.models import Organization
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from platform_audit.models import PlatformAuditEvent
from platform_audit.retention import purge_retention_days


class Command(BaseCommand):
    help = "Delete platform audit events older than the organisation's retention."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many events would be deleted without deleting them.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=5000,
            help="Events deleted per transaction (default 5000).",
        )

    def handle(self, *args, dry_run: bool = False, batch_size: int = 5000, **options):
        if batch_size < 1:
            raise CommandError("--batch-size must be at least 1.")
        now = timezone.now()
        org_ids = (
            PlatformAuditEvent.objects.values_list("organization_id", flat=True)
            .order_by()
            .distinct()
        )
        total = 0
        skipped = []
        for organization in Organization.objects.filter(id__in=list(org_ids)):
            try:
                days = purge_retention_days(organization)
            except Exception as exc:
                # Deleting by a guessed retention cannot be undone; skip it.
                skipped.append(organization.organization_id)
                self.stderr.write(
                    f"{organization.organization_id}: retention unreadable "
                    f"({type(exc).__name__}), skipped"
                )
                continue
            expired = PlatformAuditEvent.objects.filter(
                organization=organization,
                occurred_at__lt=now - timedelta(days=days),
            )
            if dry_run:
                count = expired.count()
            else:
                count = self._purge(expired, batch_size)
            total += count
            if count:
                self.stdout.write(f"{organization.organization_id}: {count}")
        verb = "would delete" if dry_run else "deleted"
        self.stdout.write(self.style.SUCCESS(f"Platform audit purge {verb} {total}."))
        if skipped:
            raise CommandError(f"Retention unreadable, skipped: {', '.join(skipped)}")

    @staticmethod
    def _purge(expired, batch_size: int) -> int:
        deleted = 0
        while True:
            ids = list(expired.values_list("id", flat=True)[:batch_size])
            if not ids:
                return deleted
            with transaction.atomic():
                deleted += PlatformAuditEvent.objects.purge(
                    PlatformAuditEvent.objects.filter(id__in=ids)
                )
