import json

import pytest
from unstract.sdk1.adapters.embedding1.gemini import GeminiEmbeddingAdapter
from unstract.sdk1.adapters.enums import AdapterTypes


class TestGeminiEmbeddingAdapter:
    def test_adapter_registration(self) -> None:
        from unstract.sdk1.adapters.embedding1 import adapters

        gemini_ids = [k for k in adapters if "gemini" in k.lower()]
        assert len(gemini_ids) == 1

    def test_get_id_format(self) -> None:
        adapter_id = GeminiEmbeddingAdapter.get_id()
        assert adapter_id.startswith("gemini|")
        # Standard UUID-4 with hyphens is 36 characters
        uuid_part = adapter_id.split("|")[1]
        assert len(uuid_part) == 36

    def test_get_adapter_type(self) -> None:
        assert GeminiEmbeddingAdapter.get_adapter_type() == AdapterTypes.EMBEDDING

    def test_get_name(self) -> None:
        assert GeminiEmbeddingAdapter.get_name() == "Gemini"

    def test_get_provider(self) -> None:
        assert GeminiEmbeddingAdapter.get_provider() == "gemini"

    def test_json_schema_loads(self) -> None:
        schema = json.loads(GeminiEmbeddingAdapter.get_json_schema())
        assert isinstance(schema, dict)
        assert "title" in schema
        assert "properties" in schema
        assert schema["title"] == "Gemini Embedding"

    def test_json_schema_required_fields(self) -> None:
        schema = json.loads(GeminiEmbeddingAdapter.get_json_schema())
        assert set(schema["required"]) == {"adapter_name", "api_key", "model"}

    def test_json_schema_no_batch_size_default(self) -> None:
        schema = json.loads(GeminiEmbeddingAdapter.get_json_schema())
        assert "default" not in schema["properties"]["embed_batch_size"]

    def test_json_schema_api_key_password_format(self) -> None:
        schema = json.loads(GeminiEmbeddingAdapter.get_json_schema())
        assert schema["properties"]["api_key"]["format"] == "password"

    def test_json_schema_model_default(self) -> None:
        schema = json.loads(GeminiEmbeddingAdapter.get_json_schema())
        assert schema["properties"]["model"]["default"] == "gemini-embedding-001"

    def test_validate_model_adds_prefix(self) -> None:
        meta = {"model": "gemini-embedding-001", "api_key": "test"}
        result = GeminiEmbeddingAdapter.validate_model(meta)
        assert result == "gemini/gemini-embedding-001"

    def test_validate_model_idempotent(self) -> None:
        meta = {"model": "gemini/gemini-embedding-001", "api_key": "test"}
        result = GeminiEmbeddingAdapter.validate_model(meta)
        assert result == "gemini/gemini-embedding-001"

    def test_validate_model_does_not_mutate_input(self) -> None:
        meta = {"model": "gemini-embedding-001", "api_key": "test"}
        GeminiEmbeddingAdapter.validate_model(meta)
        assert meta["model"] == "gemini-embedding-001"

    def test_validate_does_not_mutate_input(self) -> None:
        meta = {"model": "gemini-embedding-001", "api_key": "test-key"}
        original_model = meta["model"]
        GeminiEmbeddingAdapter.validate(meta)
        assert meta["model"] == original_model

    def test_validate_model_empty_string_raises(self) -> None:
        meta = {"model": "", "api_key": "test"}
        with pytest.raises(ValueError, match="model.*required"):
            GeminiEmbeddingAdapter.validate_model(meta)

    def test_validate_model_whitespace_only_raises(self) -> None:
        meta = {"model": "   ", "api_key": "test"}
        with pytest.raises(ValueError, match="model.*required"):
            GeminiEmbeddingAdapter.validate_model(meta)

    def test_validate_model_none_raises(self) -> None:
        meta = {"model": None, "api_key": "test"}
        with pytest.raises(ValueError, match="model.*required"):
            GeminiEmbeddingAdapter.validate_model(meta)

    def test_validate_model_missing_key_raises(self) -> None:
        meta = {"api_key": "test"}
        with pytest.raises(ValueError, match="model.*required"):
            GeminiEmbeddingAdapter.validate_model(meta)

    def test_validate_empty_model_raises(self) -> None:
        meta = {"model": "", "api_key": "test-key"}
        with pytest.raises(ValueError, match="model.*required"):
            GeminiEmbeddingAdapter.validate(meta)

    def test_validate_none_model_raises(self) -> None:
        meta = {"model": None, "api_key": "test-key"}
        with pytest.raises(ValueError, match="model.*required"):
            GeminiEmbeddingAdapter.validate(meta)

    def test_validate_missing_api_key_raises(self) -> None:
        from pydantic import ValidationError

        meta = {"model": "gemini/gemini-embedding-001"}
        with pytest.raises(ValidationError):
            GeminiEmbeddingAdapter.validate(meta)

    def test_validate_calls_validate_model(self) -> None:
        meta = {"model": "gemini-embedding-001", "api_key": "test-key"}
        validated = GeminiEmbeddingAdapter.validate(meta)
        assert validated["model"] == "gemini/gemini-embedding-001"

    def test_validate_embed_batch_size_none_by_default(self) -> None:
        meta = {"model": "gemini/gemini-embedding-001", "api_key": "test-key"}
        validated = GeminiEmbeddingAdapter.validate(meta)
        assert validated["embed_batch_size"] is None

    def test_validate_embed_batch_size_preserved(self) -> None:
        meta = {
            "model": "gemini/gemini-embedding-001",
            "api_key": "test-key",
            "embed_batch_size": 50,
        }
        validated = GeminiEmbeddingAdapter.validate(meta)
        assert validated["embed_batch_size"] == 50

    def test_validate_strips_extra_fields(self) -> None:
        meta = {
            "model": "gemini/gemini-embedding-001",
            "api_key": "test-key",
            "adapter_name": "my-adapter",
            "unknown_field": "should_be_dropped",
        }
        validated = GeminiEmbeddingAdapter.validate(meta)
        assert "adapter_name" not in validated
        assert "unknown_field" not in validated

    def test_validate_includes_base_fields(self) -> None:
        meta = {"model": "gemini/gemini-embedding-001", "api_key": "test-key"}
        validated = GeminiEmbeddingAdapter.validate(meta)
        assert "timeout" in validated
        assert "max_retries" in validated

    def test_metadata(self) -> None:
        metadata = GeminiEmbeddingAdapter.get_metadata()
        assert metadata["name"] == "Gemini"
        assert metadata["is_active"] is True
        assert metadata["adapter"] is GeminiEmbeddingAdapter
