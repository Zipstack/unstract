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


def get_lookup_configs_for_tool(tool) -> list[dict] | None:
    """Return lookup configs for a tool (single pass), or None in OSS."""
    try:
        from pluggable_apps.lookup_v1.execution import (
            build_lookup_configs_for_tool,
        )

        return build_lookup_configs_for_tool(tool)
    except ImportError:
        return None


def get_multi_var_lookups_for_tool(tool, prompt_ids=None) -> list[str]:
    """Return names of multi-variable lookups linked to the tool, [] in OSS.

    ``prompt_ids`` scopes the check to a specific subset of linked prompts
    so single / bulk runs only block when a lookup the run actually uses
    is multi-variable.
    """
    try:
        from pluggable_apps.lookup_v1.execution import has_multi_var_lookups

        _, names = has_multi_var_lookups(tool, prompt_ids=prompt_ids)
        return names
    except ImportError:
        return []


def persist_lookup_output(prompt_output, prompt_lookup: dict) -> None:
    """Persist lookup enrichment result. No-op in OSS."""
    try:
        from pluggable_apps.lookup_v1.models import LookupOutputResult

        lookup_meta = prompt_lookup.get("meta", {})
        lookup_id = lookup_meta.get("lookup_id")
        if lookup_id:
            defaults = {
                "lookup_definition_id": lookup_id,
                "output": prompt_lookup.get("enriched", ""),
            }
            version_id = lookup_meta.get("version_id")
            if version_id:
                defaults["version_id"] = version_id
            LookupOutputResult.objects.update_or_create(
                prompt_output=prompt_output,
                defaults=defaults,
            )
    except ImportError:
        pass


def enrich_prompt_output(prompt_output, data: dict) -> dict:
    """Let cloud plugins enrich serialized prompt output with lookup data.

    No-op in OSS.
    """
    try:
        from pluggable_apps.lookup_v1.output_enrichment import (
            enrich_with_lookup_output,
        )

        return enrich_with_lookup_output(prompt_output, data)
    except ImportError:
        return data


def validate_lookups_for_export(prompts) -> tuple[dict, str | None]:
    """Validate lookup assignments before export. Returns ({}, None) in OSS."""
    try:
        from pluggable_apps.lookup_v1.validation import (
            validate_lookups_for_export as _validate,
        )

        return _validate(prompts)
    except ImportError:
        return {}, None


def get_latest_lookup_mutation_for_tool(tool):
    """Return the max modified_at across all lookup-related records linked to
    the tool (version, reference file, assignment). Used for banner staleness.

    Returns None if lookups are unavailable or nothing is linked.
    """
    try:
        from pluggable_apps.lookup_v1.staleness import (
            get_latest_lookup_mutation_for_tool as _get,
        )

        return _get(tool)
    except ImportError:
        return None


def get_original_value_if_enriched(metadata: dict, prompt_key: str):
    """Return the pre-enrichment value for ``prompt_key`` if present.

    Opaque wrapper around the cloud plugin's ``lookup_outputs`` metadata
    shape so OSS callers don't need to know the key names. Returns None
    when no enrichment happened or the plugin is absent.
    """
    if not isinstance(metadata, dict):
        return None
    lookup_outputs = metadata.get("lookup_outputs") or {}
    prompt_lookup = lookup_outputs.get(prompt_key)
    if isinstance(prompt_lookup, dict) and "original" in prompt_lookup:
        return prompt_lookup.get("original"), prompt_lookup
    return None


def attach_combined_output_enrichment(result: dict, enriched_by_key: dict) -> None:
    """Stamp the combined-output payload with enriched-output metadata.

    OSS ships a stub that ignores the call; cloud reroutes into the payload
    key its FE plugin expects. Keeping the key name out of OSS lets cloud
    evolve the shape without OSS-side coordination.
    """
    try:
        from pluggable_apps.lookup_v1.output_enrichment import (
            attach_combined_output_enrichment as _attach,
        )

        _attach(result, enriched_by_key)
    except ImportError:
        return


def extract_prompt_output_enrichment(item) -> dict | None:
    """Pick enriched-output data off a serialized prompt-output row.

    Returns a plugin-opaque dict (the FE treats it as a black box) or None
    when no enrichment is present / plugin missing.
    """
    try:
        from pluggable_apps.lookup_v1.output_enrichment import (
            extract_prompt_output_enrichment as _extract,
        )

        return _extract(item)
    except ImportError:
        return None


def get_lookup_validation_for_tool(tool) -> dict:
    """Pre-emptive lookup validation for FE Export / Deploy gating.

    Returns an "always ok" payload in OSS so the FE gate is a no-op.
    """
    try:
        from pluggable_apps.lookup_v1.validation import (
            get_lookup_validation_for_tool as _validate,
        )

        return _validate(tool)
    except ImportError:
        return {
            "ok": True,
            "draft_lookups": [],
            "multi_var_lookups": [],
            "single_pass_enabled": bool(
                getattr(tool, "single_pass_extraction_mode", False)
            ),
        }
