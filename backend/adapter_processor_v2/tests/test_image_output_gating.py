"""Tests for the cloud-only gating of the LLMWhisperer image output mode.

The image-mode consumer ships only with Unstract Cloud. Without the
``plugins.vlm_image_answer`` package, the ``image`` output mode must be
hidden from the adapter's JSON schema and rejected at save/test time.
"""

import json
from pathlib import Path

import pytest
from rest_framework.exceptions import ValidationError

from adapter_processor_v2 import image_output_gating as gating
from adapter_processor_v2.image_output_gating import (
    IMAGE_OUTPUT_REQUIRES_CLOUD,
    filter_image_output_mode,
    validate_image_output_allowed,
)

_LLMW_ADAPTER_ID = "llmwhisperer|0a1647f0-f65f-410d-843b-3d979c78350e"

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "unstract/sdk1/src/unstract/sdk1/adapters/x2text/llm_whisperer_v2/src/static"
    / "json_schema.json"
)


def _llmw_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text())


@pytest.fixture
def consumer_absent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gating, "IMAGE_OUTPUT_CONSUMER_AVAILABLE", False)


@pytest.fixture
def consumer_present(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gating, "IMAGE_OUTPUT_CONSUMER_AVAILABLE", True)


class TestSchemaFiltering:
    def test_image_option_stripped_when_consumer_absent(self, consumer_absent) -> None:
        schema = _llmw_schema()
        filtered = filter_image_output_mode(_LLMW_ADAPTER_ID, schema)

        output_mode = filtered["properties"]["output_mode"]
        assert "image" not in output_mode["enum"]
        # enum / enumNames stay positionally paired
        assert len(output_mode["enum"]) == len(output_mode["enumNames"])
        assert "Image (PDF only)" not in output_mode["enumNames"]
        # The image-conditioned allOf block (conditional description) is gone
        assert not any(
            block.get("if", {}).get("properties", {}).get("output_mode", {}).get("const")
            == "image"
            for block in filtered.get("allOf", [])
        )
        # Unrelated conditional blocks are preserved
        assert any("if" in block for block in filtered.get("allOf", []))

    def test_source_schema_not_mutated(self, consumer_absent) -> None:
        schema = _llmw_schema()
        filter_image_output_mode(_LLMW_ADAPTER_ID, schema)
        assert "image" in schema["properties"]["output_mode"]["enum"]

    def test_schema_untouched_when_consumer_present(self, consumer_present) -> None:
        schema = _llmw_schema()
        assert filter_image_output_mode(_LLMW_ADAPTER_ID, schema) is schema

    def test_non_llmwhisperer_schema_untouched(self, consumer_absent) -> None:
        schema = {"properties": {"output_mode": {"enum": ["image"]}}}
        assert filter_image_output_mode("someocr|uuid", schema) is schema

    def test_schema_without_image_option_untouched(self, consumer_absent) -> None:
        schema = {"properties": {"output_mode": {"enum": ["layout_preserving"]}}}
        assert filter_image_output_mode(_LLMW_ADAPTER_ID, schema) is schema


class TestSaveTimeValidation:
    def test_image_mode_rejected_when_consumer_absent(self, consumer_absent) -> None:
        with pytest.raises(ValidationError, match="Unstract Cloud"):
            validate_image_output_allowed({"output_mode": "image"}, _LLMW_ADAPTER_ID)

    def test_error_message_names_cloud(self, consumer_absent) -> None:
        with pytest.raises(ValidationError) as excinfo:
            validate_image_output_allowed({"output_mode": "image"}, _LLMW_ADAPTER_ID)
        assert IMAGE_OUTPUT_REQUIRES_CLOUD in str(excinfo.value)

    def test_image_mode_allowed_when_consumer_present(self, consumer_present) -> None:
        validate_image_output_allowed({"output_mode": "image"}, _LLMW_ADAPTER_ID)

    def test_other_output_modes_allowed(self, consumer_absent) -> None:
        validate_image_output_allowed(
            {"output_mode": "layout_preserving"}, _LLMW_ADAPTER_ID
        )

    def test_non_llmwhisperer_adapter_allowed(self, consumer_absent) -> None:
        # Another adapter with a coincidental output_mode key is not gated.
        validate_image_output_allowed({"output_mode": "image"}, "someocr|uuid")

    def test_unknown_adapter_id_still_rejected(self, consumer_absent) -> None:
        # Metadata-only updates lack an adapter id; the metadata alone gates.
        with pytest.raises(ValidationError):
            validate_image_output_allowed({"output_mode": "image"}, None)

    def test_empty_metadata_allowed(self, consumer_absent) -> None:
        validate_image_output_allowed(None, _LLMW_ADAPTER_ID)
        validate_image_output_allowed({}, _LLMW_ADAPTER_ID)
