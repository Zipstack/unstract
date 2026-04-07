"""Shared utility for lookup operations.

Wraps cloud-only lookup calls so that OSS callers don't repeat
the try/except ImportError guard. All functions are no-ops in OSS.
"""

import logging

logger = logging.getLogger(__name__)


def get_lookup_config(prompt) -> dict | None:
    """Return lookup config for a prompt, or None if lookups are unavailable."""
    try:
        from pluggable_apps.lookup_v1.execution import (
            build_lookup_config_for_prompt,
        )

        return build_lookup_config_for_prompt(prompt)
    except ImportError:
        return None


def persist_lookup_output(prompt_output, prompt_lookup: dict) -> None:
    """Persist lookup enrichment result. No-op in OSS."""
    try:
        from pluggable_apps.lookup_v1.models import LookupOutputResult

        lookup_meta = prompt_lookup.get("meta", {})
        lookup_id = lookup_meta.get("lookup_id")
        if lookup_id:
            LookupOutputResult.objects.update_or_create(
                prompt_output=prompt_output,
                defaults={
                    "lookup_definition_id": lookup_id,
                    "output": prompt_lookup.get("enriched", ""),
                },
            )
    except ImportError:
        pass


def validate_lookups_for_export(prompts) -> tuple[dict, str | None]:
    """Validate lookup assignments before export. Returns ({}, None) in OSS."""
    try:
        from pluggable_apps.lookup_v1.validation import (
            validate_lookups_for_export as _validate,
        )

        return _validate(prompts)
    except ImportError:
        return {}, None
