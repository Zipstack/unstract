"""Shared utility for lookup operations.

Wraps cloud-only lookup calls so that OSS callers don't repeat the
try/except ImportError guard. All functions are no-ops in OSS. A single
module-level probe decides availability so downstream errors inside the
cloud plugin surface instead of being silently swallowed as ImportError.
"""

import logging

logger = logging.getLogger(__name__)

try:
    from pluggable_apps.lookup_v1 import execution as _execution
    from pluggable_apps.lookup_v1 import output_enrichment as _output_enrichment
    from pluggable_apps.lookup_v1 import staleness as _staleness
    from pluggable_apps.lookup_v1 import validation as _validation
    from pluggable_apps.lookup_v1.models import LookupOutputResult as _LookupOutputResult

    LOOKUPS_AVAILABLE = True
except ImportError:
    LOOKUPS_AVAILABLE = False


def get_lookup_config(prompt) -> dict | None:
    """Return lookup config for a prompt, or None if lookups are unavailable."""
    if not LOOKUPS_AVAILABLE:
        return None
    return _execution.build_lookup_config_for_prompt(prompt)


def get_lookup_configs_for_tool(tool, prompts=None) -> list[dict] | None:
    """Return lookup configs for a tool (single pass), or None in OSS.

    ``prompts`` scopes the build+validation to the prompts actually
    participating in the run so an unrelated incomplete assignment on
    the tool doesn't block it.
    """
    if not LOOKUPS_AVAILABLE:
        return None
    return _execution.build_lookup_configs_for_tool(tool, prompts=prompts)


def get_multi_var_lookups_for_tool(tool, prompt_ids=None) -> list[str]:
    """Return names of multi-variable lookups linked to the tool, [] in OSS.

    ``prompt_ids`` scopes the check to a specific subset of linked prompts
    so single / bulk runs only block when a lookup the run actually uses
    is multi-variable.
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
    """Return the max modified_at across all lookup-related records linked to
    the tool (version, reference file, assignment). Used for banner staleness.

    Returns None if lookups are unavailable or nothing is linked.
    """
    if not LOOKUPS_AVAILABLE:
        return None
    return _staleness.get_latest_lookup_mutation_for_tool(tool)


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
    if not LOOKUPS_AVAILABLE:
        return
    _output_enrichment.attach_combined_output_enrichment(result, enriched_by_key)


def extract_prompt_output_enrichment(item) -> dict | None:
    """Pick enriched-output data off a serialized prompt-output row.

    Returns a plugin-opaque dict (the FE treats it as a black box) or None
    when no enrichment is present / plugin missing.
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


def attach_lookup_config(output: dict, config: dict) -> None:
    """Stamp a per-prompt output dict with the lookup config payload.

    Keeps the payload key name owned by the bridge so OSS call sites
    don't encode the contract.
    """
    output["lookup_config"] = config


def attach_lookup_configs_to_tool_settings(
    tool_settings: dict, configs: list[dict]
) -> None:
    """Stamp tool_settings with the per-tool lookup configs list."""
    tool_settings["lookup_configs"] = configs


def get_lookup_config_from_output(output: dict) -> dict | None:
    """Read the lookup config stamped on a prompt output, if any."""
    return output.get("lookup_config")
