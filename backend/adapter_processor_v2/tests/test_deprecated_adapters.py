"""Guards for the adapter deprecation registry (UN-2896).

Every entry in ``DEPRECATED_ADAPTERS`` must be absent from the SDK registry and
absent from the supported-adapter listing, so a deprecated adapter cannot be
re-registered or offered for creation without this failing.
"""

from __future__ import annotations

import pytest
from rest_framework.serializers import ValidationError

from adapter_processor_v2.adapter_processor import AdapterProcessor
from adapter_processor_v2.deprecated_adapters import (
    DEPRECATED_ADAPTERS,
    get_deprecation_message,
    is_adapter_deprecated,
    is_adapter_selectable,
)
from adapter_processor_v2.exceptions import DeprecatedAdapter
from unstract.sdk1.adapters.adapterkit import Adapterkit

LLM_WHISPERER_V1 = "llmwhisperer|0a1647f0-f65f-410d-843b-3d979c78350e"

REQUIRED_METADATA_KEYS = {"reason", "deprecated_date", "adapter_name", "adapter_type"}


def test_llm_whisperer_v1_is_registered_as_deprecated():
    assert is_adapter_deprecated(LLM_WHISPERER_V1)


@pytest.mark.parametrize("adapter_id", sorted(DEPRECATED_ADAPTERS))
def test_deprecated_adapter_is_not_in_sdk_registry(adapter_id):
    """A deprecated adapter must not be registered in the SDK."""
    assert adapter_id not in Adapterkit().adapters


@pytest.mark.parametrize("adapter_id", sorted(DEPRECATED_ADAPTERS))
def test_deprecated_adapter_metadata_is_complete(adapter_id):
    assert REQUIRED_METADATA_KEYS <= set(DEPRECATED_ADAPTERS[adapter_id])


@pytest.mark.parametrize("adapter_id", sorted(DEPRECATED_ADAPTERS))
def test_deprecated_adapter_is_not_offered_for_creation(adapter_id):
    adapter_type = DEPRECATED_ADAPTERS[adapter_id]["adapter_type"]
    offered = AdapterProcessor.get_all_supported_adapters(
        user_email="someone@example.com", type=adapter_type
    )
    assert adapter_id not in {adapter["id"] for adapter in offered}


@pytest.mark.parametrize("adapter_id", sorted(DEPRECATED_ADAPTERS))
def test_json_schema_is_refused_for_deprecated_adapter(adapter_id):
    with pytest.raises(DeprecatedAdapter):
        AdapterProcessor.get_json_schema(adapter_id)


def test_deprecation_message_names_the_replacement():
    message = get_deprecation_message(LLM_WHISPERER_V1)
    assert "LLMWhisperer" in message
    assert "V2" in message


def test_unknown_adapter_is_not_deprecated():
    assert not is_adapter_deprecated("openai|some-uuid")
    assert not is_adapter_deprecated(None)


class _FakeAdapter:
    """Stand-in for AdapterInstance; is_adapter_selectable reads 4 fields."""

    def __init__(self, adapter_id, is_usable=True, is_available=True):
        self.adapter_id = adapter_id
        self.is_usable = is_usable
        self.is_available = is_available


def test_selectable_adapter_passes():
    assert is_adapter_selectable(_FakeAdapter("openai|some-uuid"))


@pytest.mark.parametrize(
    "adapter",
    [
        None,
        _FakeAdapter(LLM_WHISPERER_V1),
        _FakeAdapter("openai|some-uuid", is_usable=False),
        _FakeAdapter("openai|some-uuid", is_available=False),
    ],
    ids=["none", "deprecated", "usage-exhausted", "withdrawn-from-sdk"],
)
def test_unselectable_adapters_are_refused(adapter):
    """Guards default-profile creation and set_default_triad."""
    assert not is_adapter_selectable(adapter)


def test_serializer_rejects_deprecated_adapter_id():
    """Covers create AND update/partial_update, since adapter_id is writable."""
    from adapter_processor_v2.serializers import AdapterInstanceSerializer

    serializer = AdapterInstanceSerializer()
    with pytest.raises(ValidationError) as exc:
        serializer.validate({"adapter_id": LLM_WHISPERER_V1})
    assert "adapter_id" in exc.value.detail


def test_serializer_allows_supported_adapter_id():
    from adapter_processor_v2.serializers import AdapterInstanceSerializer

    attrs = {"adapter_id": "llmwhisperer|a5e6b8af-3e1f-4a80-b006-d017e8e67f93"}
    assert AdapterInstanceSerializer().validate(attrs) == attrs
