"""Registry of adapters that are no longer offered.

Adding an entry here is the whole deprecation: the adapter drops out of the
supported-adapter listing, creation of new instances is rejected, and profiles
can no longer be pointed at it. Existing instances keep rendering so users can
see what to migrate off.

``platform-service`` gates execution on the ``is_available`` column instead of
this registry (it is a separate service with no access to Django app code), so
a new entry needs a data migration that marks the matching rows unavailable.
"""

from typing import Any

# adapter_id ("name|uuid", as stored on AdapterInstance) -> deprecation metadata
DEPRECATED_ADAPTERS: dict[str, dict[str, Any]] = {
    "llmwhisperer|0a1647f0-f65f-410d-843b-3d979c78350e": {
        "reason": (
            "LLMWhisperer V1 is retired. Please switch to the LLMWhisperer V2 "
            "text extractor."
        ),
        "deprecated_date": "2026-08-31",
        "replacement_adapter": "LLMWhisperer V2",
        "adapter_name": "LLMWhisperer",
        "adapter_type": "X2TEXT",
    },
}


def is_adapter_deprecated(adapter_id: str | None) -> bool:
    """Whether ``adapter_id`` is a deprecated adapter."""
    return bool(adapter_id) and adapter_id in DEPRECATED_ADAPTERS


def get_deprecation_metadata(adapter_id: str | None) -> dict[str, Any] | None:
    """Deprecation metadata for ``adapter_id``, or None if it is not deprecated."""
    if not adapter_id:
        return None
    metadata = DEPRECATED_ADAPTERS.get(adapter_id)
    return dict(metadata) if metadata else None


def is_adapter_selectable(adapter: Any) -> bool:
    """Whether an ``AdapterInstance`` may back a new profile, default or config.

    Covers the three ways an adapter stops being a valid choice: usage
    exhausted (``is_usable``), withdrawn from the SDK (``is_available``), and
    deprecated here. Existing selections are not re-validated against this —
    they stay readable so users can see what to migrate off.
    """
    return bool(
        adapter is not None
        and adapter.is_usable
        and adapter.is_available
        and not is_adapter_deprecated(adapter.adapter_id)
    )


def get_deprecation_message(adapter_id: str | None) -> str:
    """User-facing reason ``adapter_id`` can no longer be used."""
    metadata = get_deprecation_metadata(adapter_id)
    if not metadata:
        return "This adapter has been deprecated and can no longer be used."
    name = metadata.get("adapter_name") or "This adapter"
    return f"{name} has been deprecated. {metadata['reason']}"
