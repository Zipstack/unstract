import json

import pytest
from unstract.sdk1.adapters.base1 import (
    NvidiaBuildEmbeddingParameters,
    NvidiaBuildLLMParameters,
    OpenAICompatibleEmbeddingParameters,
    OpenRouterLLMParameters,
)
from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.embedding1 import adapters as embedding_adapters
from unstract.sdk1.adapters.embedding1.nvidia_build import NvidiaBuildEmbeddingAdapter
from unstract.sdk1.adapters.embedding1.openai_compatible import (
    OpenAICompatibleEmbeddingAdapter,
)
from unstract.sdk1.adapters.llm1 import adapters as llm_adapters
from unstract.sdk1.adapters.llm1.nvidia_build import NvidiaBuildLLMAdapter
from unstract.sdk1.adapters.llm1.openrouter import OpenRouterLLMAdapter

_NVIDIA_BUILD_API_BASE = "https://integrate.api.nvidia.com/v1"
_OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"


# --- Branded LLM adapters -------------------------------------------------


@pytest.mark.parametrize(
    "adapter",
    [NvidiaBuildLLMAdapter, OpenRouterLLMAdapter],
)
def test_branded_llm_adapter_is_registered(adapter: type) -> None:
    adapter_id = adapter.get_id()
    assert adapter_id in llm_adapters
    assert llm_adapters[adapter_id][Common.MODULE] is adapter


@pytest.mark.parametrize(
    ("params", "default_base"),
    [
        (NvidiaBuildLLMParameters, _NVIDIA_BUILD_API_BASE),
        (OpenRouterLLMParameters, _OPENROUTER_API_BASE),
    ],
)
def test_branded_llm_prefixes_model_and_defaults_api_base(
    params: type, default_base: str
) -> None:
    validated = params.validate({"model": "some-model", "api_key": "k"})

    assert validated["model"] == "custom_openai/some-model"
    assert validated["api_base"] == default_base


@pytest.mark.parametrize(
    ("params", "default_base"),
    [
        (NvidiaBuildLLMParameters, _NVIDIA_BUILD_API_BASE),
        (OpenRouterLLMParameters, _OPENROUTER_API_BASE),
    ],
)
def test_branded_llm_blank_api_base_falls_back_to_default(
    params: type, default_base: str
) -> None:
    validated = params.validate({"model": "m", "api_key": "k", "api_base": "   "})

    assert validated["api_base"] == default_base


@pytest.mark.parametrize(
    "params",
    [NvidiaBuildLLMParameters, OpenRouterLLMParameters],
)
def test_branded_llm_honours_api_base_override(params: type) -> None:
    validated = params.validate(
        {"model": "m", "api_key": "k", "api_base": "https://proxy.internal/v1"}
    )

    assert validated["api_base"] == "https://proxy.internal/v1"


@pytest.mark.parametrize(
    ("adapter", "default_base"),
    [
        (NvidiaBuildLLMAdapter, _NVIDIA_BUILD_API_BASE),
        (OpenRouterLLMAdapter, _OPENROUTER_API_BASE),
    ],
)
def test_branded_llm_schema_exposes_api_base_with_default(
    adapter: type, default_base: str
) -> None:
    schema = json.loads(adapter.get_json_schema())

    assert schema["properties"]["api_base"]["default"] == default_base
    assert "api_base" not in schema["required"]
    assert "model" in schema["required"]


# --- Branded / generic embedding adapters ---------------------------------


def test_nvidia_embedding_registered_and_routes_via_nvidia_nim() -> None:
    adapter_id = NvidiaBuildEmbeddingAdapter.get_id()
    assert adapter_id in embedding_adapters

    validated = NvidiaBuildEmbeddingParameters.validate(
        {"model": "nvidia/nv-embedqa-e5-v5", "api_key": "k"}
    )
    assert validated["model"] == "nvidia_nim/nvidia/nv-embedqa-e5-v5"
    assert validated["api_base"] == _NVIDIA_BUILD_API_BASE


def test_nvidia_embedding_honours_api_base_override() -> None:
    validated = NvidiaBuildEmbeddingParameters.validate(
        {"model": "m", "api_key": "k", "api_base": "https://proxy.internal/v1"}
    )
    assert validated["api_base"] == "https://proxy.internal/v1"


def test_nvidia_embedding_model_prefix_is_idempotent() -> None:
    once = NvidiaBuildEmbeddingParameters.validate({"model": "m", "api_key": "k"})
    twice = NvidiaBuildEmbeddingParameters.validate(dict(once))
    assert twice["model"] == once["model"] == "nvidia_nim/m"


def test_compatible_embedding_registered_and_routes_via_openai() -> None:
    adapter_id = OpenAICompatibleEmbeddingAdapter.get_id()
    assert adapter_id in embedding_adapters
    assert OpenAICompatibleEmbeddingAdapter.get_provider() == "custom_openai"

    validated = OpenAICompatibleEmbeddingParameters.validate(
        {"model": "BAAI/bge-m3", "api_base": "https://gw.example/v1"}
    )
    assert validated["model"] == "openai/BAAI/bge-m3"
    assert validated["api_base"] == "https://gw.example/v1"


def test_compatible_embedding_blank_api_key_normalized_to_none() -> None:
    validated = OpenAICompatibleEmbeddingParameters.validate(
        {"model": "m", "api_base": "https://gw.example/v1", "api_key": "  "}
    )
    assert validated["api_key"] is None


def test_compatible_embedding_requires_api_base() -> None:
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        OpenAICompatibleEmbeddingParameters.validate({"model": "m"})


def test_compatible_embedding_schema_loadable() -> None:
    schema = json.loads(OpenAICompatibleEmbeddingAdapter.get_json_schema())
    assert schema["title"] == "OpenAI Compatible Embedding"
    assert "api_base" in schema["required"]
    assert "model" in schema["required"]
