"""Lookup enrichment + webhook postprocessing helpers.

Extracted from ``LegacyExecutor`` so the orchestrator stays focused on
dispatch. Both helpers are free functions — callers pass shim/state in.
"""

from __future__ import annotations

import logging
from typing import Any

from executor.executors.constants import PromptServiceConstants as PSKeys
from executor.executors.plugins import ExecutorPluginLoader

from unstract.sdk1.constants import LogLevel

logger = logging.getLogger(__name__)


def is_blank(value: Any) -> bool:
    """Treat None / whitespace strings / empty containers as no-value.

    Boolean False / numeric 0 are NOT blank — valid inputs for
    boolean/number prompts whose lookups should still run.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


def run_lookup_enrichment(
    output: dict[str, Any],
    structured_output: dict[str, Any],
    metadata: dict[str, Any],
    metrics: dict[str, Any],
    shim: Any,
    llm_cls: Any,
    usage_kwargs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run lookup enrichment plugin if enabled and available.

    Returns any usage records the plugin emitted (recovered even on
    plugin failure) so the caller can extend its billing batch.
    """
    prompt_name = output[PSKeys.NAME]
    current_value = structured_output.get(prompt_name)

    lookup_config = output.get("lookup_config")
    lookup_cls = ExecutorPluginLoader.get("lookup-enrichment")
    if not (lookup_config and lookup_cls):
        return []
    if is_blank(current_value):
        # Surface a skip log instead of silently no-op-ing.
        lookup_name = lookup_config.get("lookup_name") or "lookup"
        shim.stream_log(
            f"Skipping lookup `{lookup_name}` for `{prompt_name}` — "
            f"source prompt produced no value."
        )
        return []

    outcome = None
    try:
        outcome = lookup_cls.run_with_metrics(
            llm_cls=llm_cls,
            lookup_config=lookup_config,
            structured_output=structured_output,
            current_value=current_value,
            metadata=metadata,
            prompt_name=prompt_name,
            shim=shim,
            usage_kwargs=usage_kwargs,
        )
        metrics.setdefault(prompt_name, {})[lookup_cls.METRICS_KEY] = outcome.llm_metrics
    except Exception:
        # Degrade gracefully on plugin contract drift.
        lookup_name = lookup_config.get("lookup_name") or "lookup"
        logger.exception(
            "Lookup enrichment failed for prompt=%s lookup=%s",
            prompt_name,
            lookup_name,
        )
        shim.stream_log(
            f"Lookup `{lookup_name}` failed for `{prompt_name}`; "
            f"continuing without enrichment.",
            level=LogLevel.WARN,
        )

    if outcome is not None and getattr(outcome, "usage_records", None):
        return list(outcome.usage_records)
    return []


def run_webhook_postprocessing(
    output: dict[str, Any],
    structured_output: dict[str, Any],
    metadata: dict[str, Any],
    shim: Any,
) -> None:
    """Run webhook postprocessing if enabled (JSON outputs only)."""
    from executor.executors.answer_prompt import AnswerPromptService

    prompt_name = output[PSKeys.NAME]
    output_type = output.get(PSKeys.TYPE, "")
    webhook_enabled = output.get(PSKeys.ENABLE_POSTPROCESSING_WEBHOOK, False)
    if not webhook_enabled:
        return
    # Empty / non-JSON payloads are skipped — typically a parse failure.
    parsed_value = structured_output.get(prompt_name)
    if not isinstance(parsed_value, (dict, list)) or not parsed_value:
        logger.warning(
            "Webhook postprocessing skipped: prompt=%s parsed payload "
            "is empty or non-JSON (likely a parse failure)",
            prompt_name,
        )
        return
    if output_type != PSKeys.JSON:
        logger.warning(
            "Webhook postprocessing supports JSON outputs only; "
            "skipping for prompt=%s (output_type=%s)",
            prompt_name,
            output_type,
        )
        shim.stream_log(
            f"Webhook postprocessing supports JSON outputs only; "
            f"skipping for `{prompt_name}`.",
            level=LogLevel.WARN,
        )
        return

    webhook_url = output.get(PSKeys.POSTPROCESSING_WEBHOOK_URL)
    highlight_data = None
    if metadata and PSKeys.HIGHLIGHT_DATA in metadata:
        highlight_data = metadata.get(PSKeys.HIGHLIGHT_DATA, {}).get(prompt_name)
    processed, updated_highlights = AnswerPromptService._run_webhook_postprocess(
        parsed_data=structured_output.get(prompt_name),
        webhook_url=webhook_url,
        highlight_data=highlight_data,
    )
    structured_output[prompt_name] = processed
    if updated_highlights is not None and metadata:
        metadata.setdefault(PSKeys.HIGHLIGHT_DATA, {})[prompt_name] = updated_highlights
