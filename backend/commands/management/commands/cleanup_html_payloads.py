"""Replace stored HTML/JS payloads in name/description columns.

Targets the columns flagged by the May 2026 prod scan against US prod, where
all matches were pentest leftovers. See KB
`Obsidian Vault/zipstuff/UN-3393-input-validation/05-prod-baseline.md` for the
scan methodology.

Default mode is `--dry-run`: print id + table + column + truncated value for
every row that would be replaced. Pass `--apply` to perform the replacement
inside a single transaction. The replacement value is `REPLACEMENT`.

Usage:
    python manage.py cleanup_html_payloads               # dry-run
    python manage.py cleanup_html_payloads --apply       # apply
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from utils.input_sanitizer import (
    EVENT_HANDLER_PATTERN,
    HTML_TAG_PATTERN,
    JS_PROTOCOL_PATTERN,
)

REPLACEMENT = "[removed-invalid-content]"
PREVIEW_CHARS = 160

# (app_label, model_name, column_name) — resolved dynamically to keep this
# command independent of import-order between apps and pluggable_apps.
TARGETS: tuple[tuple[str, str, str], ...] = (
    ("prompt_studio_core_v2", "CustomTool", "tool_name"),
    ("prompt_studio_core_v2", "CustomTool", "description"),
    ("workflow_v2", "Workflow", "workflow_name"),
    ("workflow_v2", "Workflow", "description"),
    ("api_v2", "APIDeployment", "display_name"),
    ("api_v2", "APIDeployment", "description"),
    ("adapter_processor_v2", "AdapterInstance", "adapter_name"),
)


def _has_payload(value: str | None) -> bool:
    if not value:
        return False
    return bool(
        HTML_TAG_PATTERN.search(value)
        or JS_PROTOCOL_PATTERN.search(value)
        or EVENT_HANDLER_PATTERN.search(value)
    )


class Command(BaseCommand):
    help = (
        "Replace stored HTML/JS payloads in known name/description columns "
        "with a redaction marker. Default mode is --dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Perform the replacement. Without this flag, the command only prints candidates.",
        )

    def handle(self, *args, **opts):
        from django.apps import apps

        apply = opts["apply"]
        total = 0
        replaced = 0

        for app_label, model_name, column in TARGETS:
            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                self.stderr.write(f"[skip] {app_label}.{model_name} not installed")
                continue

            qs = model.objects.exclude(**{f"{column}__isnull": True}).exclude(
                **{column: ""}
            )
            matches: list[tuple[object, str]] = []
            for obj in qs.only("id", column).iterator():
                value = getattr(obj, column)
                if _has_payload(value):
                    matches.append((obj.id, value))

            if not matches:
                continue

            label = f"{app_label}.{model_name}.{column}"
            self.stdout.write(f"\n=== {label}: {len(matches)} match(es) ===")
            for obj_id, value in matches:
                preview = value[:PREVIEW_CHARS].replace("\n", " ")
                self.stdout.write(f"  id={obj_id}  value={preview!r}")
            total += len(matches)

            if apply:
                with transaction.atomic():
                    updated = model.objects.filter(
                        id__in=[obj_id for obj_id, _ in matches]
                    ).update(**{column: REPLACEMENT})
                replaced += updated
                self.stdout.write(
                    self.style.SUCCESS(f"  applied: replaced {updated} row(s)")
                )

        self.stdout.write("")
        if apply:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. Replaced {replaced} row(s) across {len(TARGETS)} target column(s)."
                )
            )
        else:
            self.stdout.write(
                f"Dry run. {total} candidate row(s) across {len(TARGETS)} target column(s). "
                "Re-run with --apply to perform the replacement."
            )
