import json

import pytest

from unstract.sdk1.adapters.embedding1.mistral import MistralEmbeddingAdapter
from unstract.sdk1.adapters.enums import AdapterTypes


class TestMistralEmbeddingAdapter:
    def test_adapter_registration(self) -> None:
        from unstract.sdk1.adapters.embedding1 import adapters

        mistral_ids = [k for k in adapters if "mistral" in k.lower()]
        assert len(mistral_ids) == 1

    def test_get_id_format(self) -> None:
        adapter_id = MistralEmbeddingAdapter.get_id()
        assert adapter_id.startswith("mistral|")
        # Standard UUID-4 with hyphens is 36 characters
        uuid_part = adapter_id.split("|")[1]
        assert len(uuid_part) == 36

    def test_get_adapter_type(self) -> None:
        assert MistralEmbeddingAdapter.get_adapter_type() == AdapterTypes.EMBEDDING

    def test_get_name(self) -> None:
        assert MistralEmbeddingAdapter.get_name() == "Mistral"

    def test_get_provider(self) -> None:
        assert MistralEmbeddingAdapter.get_provider() == "mistral"

    def test_json_schema_loads(self) -> None:
        schema = json.loads(MistralEmbeddingAdapter.get_json_schema())
        assert isinstance(schema, dict)
        assert "title" in schema
        assert "properties" in schema
        assert schema["title"] == "Mistral Embedding"

    def test_json_schema_required_fields(self) -> None:
        schema = json.loads(MistralEmbeddingAdapter.get_json_schema())
        assert set(schema["required"]) == {"adapter_name", "api_key", "model"}

    def test_json_schema_omits_batch_size(self) -> None:
        # embed_batch_size is an inert client-side hint and is not exposed.
        schema = json.loads(MistralEmbeddingAdapter.get_json_schema())
        assert "embed_batch_size" not in schema["properties"]

    def test_json_schema_api_key_password_format(self) -> None:
        schema = json.loads(MistralEmbeddingAdapter.get_json_schema())
        assert schema["properties"]["api_key"]["format"] == "password"

    def test_json_schema_model_default(self) -> None:
        schema = json.loads(MistralEmbeddingAdapter.get_json_schema())
        assert schema["properties"]["model"]["default"] == "mistral-embed"

    def test_validate_model_adds_prefix(self) -> None:
        meta = {"model": "mistral-embed", "api_key": "test"}
        result = MistralEmbeddingAdapter.validate_model(meta)
        assert result == "mistral/mistral-embed"

    def test_validate_model_idempotent(self) -> None:
        meta = {"model": "mistral/mistral-embed", "api_key": "test"}
        result = MistralEmbeddingAdapter.validate_model(meta)
        assert result == "mistral/mistral-embed"

    def test_validate_model_does_not_mutate_input(self) -> None:
        meta = {"model": "mistral-embed", "api_key": "test"}
        MistralEmbeddingAdapter.validate_model(meta)
        assert meta["model"] == "mistral-embed"

    def test_validate_does_not_mutate_input(self) -> None:
        meta = {"model": "mistral-embed", "api_key": "test-key"}
        original_model = meta["model"]
        MistralEmbeddingAdapter.validate(meta)
        assert meta["model"] == original_model

    def test_validate_model_empty_string_raises(self) -> None:
        meta = {"model": "", "api_key": "test"}
        with pytest.raises(ValueError, match="model.*required"):
            MistralEmbeddingAdapter.validate_model(meta)

    def test_validate_model_whitespace_only_raises(self) -> None:
        meta = {"model": "   ", "api_key": "test"}
        with pytest.raises(ValueError, match="model.*required"):
            MistralEmbeddingAdapter.validate_model(meta)

    def test_validate_model_none_raises(self) -> None:
        meta = {"model": None, "api_key": "test"}
        with pytest.raises(ValueError, match="model.*required"):
            MistralEmbeddingAdapter.validate_model(meta)

    def test_validate_model_missing_key_raises(self) -> None:
        meta = {"api_key": "test"}
        with pytest.raises(ValueError, match="model.*required"):
            MistralEmbeddingAdapter.validate_model(meta)

    def test_validate_empty_model_raises(self) -> None:
        meta = {"model": "", "api_key": "test-key"}
        with pytest.raises(ValueError, match="model.*required"):
            MistralEmbeddingAdapter.validate(meta)

    def test_validate_none_model_raises(self) -> None:
        meta = {"model": None, "api_key": "test-key"}
        with pytest.raises(ValueError, match="model.*required"):
            MistralEmbeddingAdapter.validate(meta)

    def test_validate_missing_api_key_raises(self) -> None:
        from pydantic import ValidationError

        meta = {"model": "mistral/mistral-embed"}
        with pytest.raises(ValidationError):
            MistralEmbeddingAdapter.validate(meta)

    def test_validate_calls_validate_model(self) -> None:
        meta = {"model": "mistral-embed", "api_key": "test-key"}
        validated = MistralEmbeddingAdapter.validate(meta)
        assert validated["model"] == "mistral/mistral-embed"

    def test_validate_strips_extra_fields(self) -> None:
        meta = {
            "model": "mistral/mistral-embed",
            "api_key": "test-key",
            "adapter_name": "my-adapter",
            "unknown_field": "should_be_dropped",
        }
        validated = MistralEmbeddingAdapter.validate(meta)
        assert "adapter_name" not in validated
        assert "unknown_field" not in validated

    def test_validate_includes_base_fields(self) -> None:
        meta = {"model": "mistral/mistral-embed", "api_key": "test-key"}
        validated = MistralEmbeddingAdapter.validate(meta)
        assert "timeout" in validated
        assert "max_retries" in validated

    def test_metadata(self) -> None:
        metadata = MistralEmbeddingAdapter.get_metadata()
        assert metadata["name"] == "Mistral"
        assert metadata["is_active"] is True
        assert metadata["adapter"] is MistralEmbeddingAdapter
