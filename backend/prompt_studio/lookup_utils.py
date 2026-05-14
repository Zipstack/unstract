"""Shared utility for lookup operations. No-ops in OSS.

Only the absence of ``pluggable_apps.lookups`` itself is treated as
"cloud not installed"; an ImportError from a transitive dependency
re-raises so we don't silently degrade to a no-op on a real bug.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

_CLOUD_LOOKUP_MODULES = {
    # OSS images lack the parent ``pluggable_apps`` package, so include it.
    "pluggable_apps",
    "pluggable_apps.lookups",
    "pluggable_apps.lookups.execution",
    "pluggable_apps.lookups.output_enrichment",
    "pluggable_apps.lookups.staleness",
    "pluggable_apps.lookups.validation",
    "pluggable_apps.lookups.models",
}

try:
    from pluggable_apps.lookups import execution as _execution
    from pluggable_apps.lookups import output_enrichment as _output_enrichment
    from pluggable_apps.lookups import staleness as _staleness
    from pluggable_apps.lookups import validation as _validation
    from pluggable_apps.lookups.models import LookupOutputResult as _LookupOutputResult

    LOOKUPS_AVAILABLE = True
except ImportError as e:
    if e.name not in _CLOUD_LOOKUP_MODULES:
        raise
    LOOKUPS_AVAILABLE = False


def get_lookup_config(prompt) -> dict | None:
    """Return lookup config for a prompt, or None if lookups are unavailable."""
    if not LOOKUPS_AVAILABLE:
        return None
    return _execution.build_lookup_config_for_prompt(prompt)


def get_lookup_configs_for_tool(tool, prompts=None) -> list[dict] | None:
    """Return lookup configs for a tool (single pass), or None in OSS.

    ``prompts`` scopes validation to the run's prompts so unrelated
    incomplete assignments on the tool don't block it.
    """
    if not LOOKUPS_AVAILABLE:
        return None
    return _execution.build_lookup_configs_for_tool(tool, prompts=prompts)


def get_multi_var_lookups_for_tool(tool, prompt_ids=None) -> list[str]:
    """Return names of multi-variable lookups linked to the tool, [] in OSS.

    ``prompt_ids`` scopes the check so a run is only blocked when the
    multi-var lookup is actually used by it.
    """
    if not LOOKUPS_AVAILABLE:
        return []
    _, names = _execution.has_multi_var_lookups(tool, prompt_ids=prompt_ids)
    return names


def persist_lookup_output(prompt_output, prompt_lookup: dict) -> None:
    """Persist lookup enrichment result. No-op in OSS."""
    if not LOOKUPS_AVAILABLE:
        return
    lookup_meta = prompt_lookup.get("meta", {})
    lookup_id = lookup_meta.get("lookup_id")
    if not lookup_id:
        return
    defaults = {
        "lookup_definition_id": lookup_id,
        "output": prompt_lookup.get("enriched", ""),
    }
    version_id = lookup_meta.get("version_id")
    if version_id:
        defaults["version_id"] = version_id
    _LookupOutputResult.objects.update_or_create(
        prompt_output=prompt_output,
        defaults=defaults,
    )


def enrich_prompt_output(prompt_output, data: dict) -> dict:
    """Let cloud plugins enrich serialized prompt output with lookup data.

    No-op in OSS.
    """
    if not LOOKUPS_AVAILABLE:
        return data
    return _output_enrichment.enrich_with_lookup_output(prompt_output, data)


def validate_lookups_for_export(prompts) -> tuple[dict, str | None]:
    """Validate lookup assignments before export. Returns ({}, None) in OSS."""
    if not LOOKUPS_AVAILABLE:
        return {}, None
    return _validation.validate_lookups_for_export(prompts)


def get_latest_lookup_mutation_for_tool(tool):
    """Max ``modified_at`` across lookup-related records linked to the tool
    (version, reference file, assignment) — feeds the staleness banner.
    None if unavailable or nothing linked.
    """
    if not LOOKUPS_AVAILABLE:
        return None
    return _staleness.get_latest_lookup_mutation_for_tool(tool)


def get_original_value_if_enriched(
    metadata: dict, prompt_key: str
) -> tuple[Any, dict] | None:
    """Return ``(original_value, prompt_lookup_dict)`` if ``prompt_key`` was
    enriched, or ``None`` otherwise.

    Pure metadata-shape check — safe to call even when LOOKUPS_AVAILABLE
    is False (returns None because the shape won't match).
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

    Key name stays cloud-side so the FE-plugin shape can evolve without
    coordinating with OSS.
    """
    if not LOOKUPS_AVAILABLE:
        return
    _output_enrichment.attach_combined_output_enrichment(result, enriched_by_key)


def extract_prompt_output_enrichment(item) -> dict | None:
    """Pick enriched-output data off a serialized prompt-output row.

    Returns a plugin-opaque dict (FE-only) or None when no enrichment
    is present / plugin missing.
    """
    if not LOOKUPS_AVAILABLE:
        return None
    return _output_enrichment.extract_prompt_output_enrichment(item)


def get_lookup_validation_for_tool(tool) -> dict:
    """Pre-emptive lookup validation for FE Export / Deploy gating.

    Returns an "always ok" payload in OSS so the FE gate is a no-op.
    """
    if not LOOKUPS_AVAILABLE:
        return {
            "ok": True,
            "draft_lookups": [],
            "multi_var_lookups": [],
            "incomplete_lookups": [],
            "single_pass_enabled": bool(
                getattr(tool, "single_pass_extraction_mode", False)
            ),
        }
    return _validation.get_lookup_validation_for_tool(tool)
