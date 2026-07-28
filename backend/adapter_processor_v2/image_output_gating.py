"""Gating for the LLMWhisperer image output mode.

Image output mode produces per-page PNGs that are consumed by the VLM answer
plugin, which ships only with Unstract Cloud. On deployments without the
``plugins.vlm_image_answer`` package the mode is hidden from the adapter's
JSON schema and rejected at save/test time, so users cannot configure a
per-page billed extraction whose output nothing can consume.
"""

import copy
import logging
from typing import Any

from rest_framework.exceptions import ValidationError

from unstract.sdk1.adapters.x2text.constants import ImageOutputConstants

logger = logging.getLogger(__name__)

LLMWHISPERER_ADAPTER_PREFIX = "llmwhisperer|"
IMAGE_OUTPUT_REQUIRES_CLOUD = (
    "The 'image' output mode is available only on Unstract Cloud."
)


def _consumer_plugin_available() -> bool:
    try:
        import plugins.vlm_image_answer  # noqa: F401
    except ImportError:
        return False
    return True


IMAGE_OUTPUT_CONSUMER_AVAILABLE = _consumer_plugin_available()


def _is_image_mode_condition(block: dict[str, Any]) -> bool:
    """True if an ``allOf`` block is conditioned on the image output mode."""
    const = (
        block.get("if", {})
        .get("properties", {})
        .get(ImageOutputConstants.OUTPUT_MODE, {})
        .get("const")
    )
    return const == ImageOutputConstants.IMAGE_MODE


def filter_image_output_mode(adapter_id: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Strip the image output-mode option from an adapter's JSON schema.

    No-op when the consumer plugin is available, for non-LLMWhisperer
    adapters, or when the schema has no image option. Returns a filtered
    deep copy otherwise (the SDK-provided schema is shared state).
    """
    if IMAGE_OUTPUT_CONSUMER_AVAILABLE:
        return schema
    if not adapter_id.startswith(LLMWHISPERER_ADAPTER_PREFIX):
        return schema
    output_mode = schema.get("properties", {}).get(ImageOutputConstants.OUTPUT_MODE, {})
    if ImageOutputConstants.IMAGE_MODE not in output_mode.get("enum", []):
        return schema

    schema = copy.deepcopy(schema)
    output_mode = schema["properties"][ImageOutputConstants.OUTPUT_MODE]
    idx = output_mode["enum"].index(ImageOutputConstants.IMAGE_MODE)
    output_mode["enum"].pop(idx)
    enum_names = output_mode.get("enumNames")
    if enum_names and len(enum_names) > idx:
        enum_names.pop(idx)
    if "allOf" in schema:
        schema["allOf"] = [
            block for block in schema["allOf"] if not _is_image_mode_condition(block)
        ]
    return schema


def validate_image_output_allowed(
    adapter_metadata: dict[str, Any] | None, adapter_id: str | None = None
) -> None:
    """Reject image output mode when the consumer plugin is unavailable.

    Backstop for the schema filtering above: covers adapters created or
    updated via the API (bypassing the UI form) and test-connection calls.
    When ``adapter_id`` is unknown (e.g. a metadata-only update) the check
    falls back to the metadata alone — only the LLMWhisperer V2 adapter
    exposes an ``image`` output mode.
    """
    if IMAGE_OUTPUT_CONSUMER_AVAILABLE or not adapter_metadata:
        return
    if (
        adapter_metadata.get(ImageOutputConstants.OUTPUT_MODE)
        != ImageOutputConstants.IMAGE_MODE
    ):
        return
    if adapter_id is not None and not adapter_id.startswith(LLMWHISPERER_ADAPTER_PREFIX):
        return
    raise ValidationError(IMAGE_OUTPUT_REQUIRES_CLOUD)
