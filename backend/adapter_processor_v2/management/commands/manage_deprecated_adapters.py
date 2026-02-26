"""Django management command for managing deprecated adapters.

Usage:
    python manage.py manage_deprecated_adapters --list
    python manage.py manage_deprecated_adapters --mark-deprecated <uuid> --reason "Deprecated message"
    python manage.py manage_deprecated_adapters --restore <uuid>
    python manage.py manage_deprecated_adapters --report
"""

import json
import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from adapter_processor_v2.models import AdapterInstance

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Manage deprecated adapters in the system"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--list",
            action="store_true",
            help="List all deprecated adapters",
        )
        parser.add_argument(
            "--mark-deprecated",
            type=str,
            help="Mark adapter as deprecated by UUID",
        )
        parser.add_argument(
            "--restore",
            type=str,
            help="Restore deprecated adapter by UUID",
        )
        parser.add_argument(
            "--reason",
            type=str,
            help="Reason for deprecation (required with --mark-deprecated)",
        )
        parser.add_argument(
            "--replacement",
            type=str,
            help="Suggested replacement adapter ID (optional)",
        )
        parser.add_argument(
            "--report",
            action="store_true",
            help="Generate comprehensive deprecation report",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Main command handler."""
        if options["list"]:
            self._list_deprecated()
        elif options["mark_deprecated"]:
            self._mark_deprecated(
                options["mark_deprecated"],
                options.get("reason"),
                options.get("replacement"),
            )
        elif options["restore"]:
            self._restore_adapter(options["restore"])
        elif options["report"]:
            self._generate_report()
        else:
            raise CommandError(
                "Please specify an action: --list, --mark-deprecated, --restore, or --report"
            )

    def _list_deprecated(self) -> None:
        """List all deprecated adapters."""
        deprecated_adapters = AdapterInstance.objects.filter(is_available=False)

        if not deprecated_adapters.exists():
            self.stdout.write(self.style.SUCCESS("No deprecated adapters found."))
            return

        self.stdout.write(
            self.style.WARNING(
                f"\nFound {deprecated_adapters.count()} deprecated adapters:\n"
            )
        )

        for adapter in deprecated_adapters:
            self.stdout.write(f"\n{'=' * 80}")
            self.stdout.write(f"UUID: {adapter.id}")
            self.stdout.write(f"Name: {adapter.adapter_name}")
            self.stdout.write(f"Type: {adapter.adapter_type}")
            self.stdout.write(f"SDK ID: {adapter.adapter_id}")

            if adapter.deprecation_metadata:
                self.stdout.write("\nDeprecation Details:")
                for key, value in adapter.deprecation_metadata.items():
                    self.stdout.write(f"  {key}: {value}")

            # Check if it's being used
            usage_count = self._check_usage(adapter)
            if usage_count > 0:
                self.stdout.write(
                    self.style.ERROR(f"⚠️  Used by {usage_count} configuration(s)")
                )
            else:
                self.stdout.write(self.style.SUCCESS("✓ Not currently in use"))

    @transaction.atomic
    def _mark_deprecated(
        self, adapter_uuid: str, reason: str | None, replacement: str | None
    ) -> None:
        """Mark an adapter as deprecated."""
        if not reason:
            raise CommandError(
                "--reason is required when marking an adapter as deprecated"
            )

        try:
            adapter = AdapterInstance.objects.get(id=adapter_uuid)
        except AdapterInstance.DoesNotExist:
            raise CommandError(f"Adapter with UUID {adapter_uuid} not found")

        if not adapter.is_available:
            self.stdout.write(
                self.style.WARNING(
                    f"Adapter {adapter.adapter_name} is already deprecated"
                )
            )
            return

        # Check usage before deprecating
        usage_count = self._check_usage(adapter)
        if usage_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠️  WARNING: This adapter is currently used by {usage_count} configuration(s).\n"
                    "Deprecating it will prevent SDK calls but won't remove existing configurations.\n"
                )
            )
            confirm = input("Continue? (yes/no): ")
            if confirm.lower() != "yes":
                self.stdout.write(self.style.ERROR("Operation cancelled"))
                return

        # Build deprecation metadata
        from datetime import datetime

        deprecation_metadata = {
            "reason": reason,
            "deprecated_date": datetime.now().strftime("%Y-%m-%d"),
            "adapter_name": adapter.adapter_id,
            "adapter_type": adapter.adapter_type,
        }
        if replacement:
            deprecation_metadata["replacement_adapter"] = replacement

        # Mark as deprecated
        adapter.is_available = False
        adapter.deprecation_metadata = deprecation_metadata
        adapter.save(update_fields=["is_available", "deprecation_metadata"])

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Successfully marked {adapter.adapter_name} as deprecated\n"
            )
        )
        self.stdout.write("Deprecation metadata:")
        self.stdout.write(json.dumps(deprecation_metadata, indent=2))

        logger.info(
            f"Adapter {adapter.adapter_name} ({adapter.id}) marked as deprecated. "
            f"Reason: {reason}"
        )

    @transaction.atomic
    def _restore_adapter(self, adapter_uuid: str) -> None:
        """Restore a deprecated adapter."""
        try:
            adapter = AdapterInstance.objects.get(id=adapter_uuid)
        except AdapterInstance.DoesNotExist:
            raise CommandError(f"Adapter with UUID {adapter_uuid} not found")

        if adapter.is_available:
            self.stdout.write(
                self.style.WARNING(f"Adapter {adapter.adapter_name} is not deprecated")
            )
            return

        old_metadata = adapter.deprecation_metadata

        # Restore adapter
        adapter.is_available = True
        adapter.deprecation_metadata = None
        adapter.save(update_fields=["is_available", "deprecation_metadata"])

        self.stdout.write(
            self.style.SUCCESS(f"\n✓ Successfully restored {adapter.adapter_name}\n")
        )
        if old_metadata:
            self.stdout.write("Previous deprecation metadata:")
            self.stdout.write(json.dumps(old_metadata, indent=2))

        logger.info(
            f"Adapter {adapter.adapter_name} ({adapter.id}) restored from deprecation"
        )

    def _check_usage(self, adapter: AdapterInstance) -> int:
        """Check if adapter is being used in any configurations.

        Returns:
            Number of places where adapter is being used
        """
        usage_count = 0

        # Check if it's a default adapter for any user
        from adapter_processor_v2.models import UserDefaultAdapter

        if adapter.adapter_type == "LLM":
            usage_count += UserDefaultAdapter.objects.filter(
                default_llm_adapter=adapter
            ).count()
        elif adapter.adapter_type == "EMBEDDING":
            usage_count += UserDefaultAdapter.objects.filter(
                default_embedding_adapter=adapter
            ).count()
        elif adapter.adapter_type == "VECTOR_DB":
            usage_count += UserDefaultAdapter.objects.filter(
                default_vector_db_adapter=adapter
            ).count()
        elif adapter.adapter_type == "X2TEXT":
            usage_count += UserDefaultAdapter.objects.filter(
                default_x2text_adapter=adapter
            ).count()

        # Check if shared with users
        usage_count += adapter.shared_users.count()

        # Check if shared to organization
        if adapter.shared_to_org:
            usage_count += 1

        return usage_count

    def _generate_report(self) -> None:
        """Generate comprehensive deprecation report."""
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 80))
        self.stdout.write(self.style.SUCCESS("DEPRECATED ADAPTERS REPORT"))
        self.stdout.write(self.style.SUCCESS("=" * 80 + "\n"))

        # Overall statistics
        total_adapters = AdapterInstance.objects.count()
        deprecated_adapters = AdapterInstance.objects.filter(is_available=False)
        deprecated_count = deprecated_adapters.count()

        self.stdout.write(f"Total adapters: {total_adapters}")
        self.stdout.write(f"Deprecated adapters: {deprecated_count}")
        self.stdout.write(
            f"Deprecation rate: {(deprecated_count / total_adapters * 100):.1f}%\n"
            if total_adapters > 0
            else "N/A\n"
        )

        # Group by type
        self.stdout.write("Deprecated adapters by type:")
        for adapter_type in ["LLM", "EMBEDDING", "VECTOR_DB", "X2TEXT", "OCR"]:
            count = deprecated_adapters.filter(adapter_type=adapter_type).count()
            if count > 0:
                self.stdout.write(f"  {adapter_type}: {count}")

        # Adapters with usage
        self.stdout.write("\nDeprecated adapters still in use:")
        in_use = []
        for adapter in deprecated_adapters:
            usage = self._check_usage(adapter)
            if usage > 0:
                in_use.append((adapter, usage))

        if in_use:
            for adapter, usage in sorted(in_use, key=lambda x: x[1], reverse=True):
                self.stdout.write(
                    self.style.WARNING(
                        f"  {adapter.adapter_name} ({adapter.adapter_type}): "
                        f"{usage} usage(s)"
                    )
                )
        else:
            self.stdout.write(self.style.SUCCESS("  None"))

        # Replacement suggestions
        self.stdout.write("\nReplacement suggestions available:")
        with_replacements = deprecated_adapters.exclude(
            deprecation_metadata__isnull=True
        ).exclude(deprecation_metadata__replacement_adapter__isnull=True)

        if with_replacements.exists():
            for adapter in with_replacements:
                replacement = adapter.deprecation_metadata.get("replacement_adapter")
                self.stdout.write(f"  {adapter.adapter_name} → {replacement}")
        else:
            self.stdout.write("  None")

        self.stdout.write("\n" + "=" * 80 + "\n")
