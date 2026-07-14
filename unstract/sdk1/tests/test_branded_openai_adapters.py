import json

import pytest
from unstract.sdk1.adapters.base1 import (
    MiniMaxLLMParameters,
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
from unstract.sdk1.adapters.llm1.minimax import MiniMaxLLMAdapter
from unstract.sdk1.adapters.llm1.nvidia_build import NvidiaBuildLLMAdapter
from unstract.sdk1.adapters.llm1.openrouter import OpenRouterLLMAdapter

_NVIDIA_BUILD_API_BASE = "https://integrate.api.nvidia.com/v1"
_OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
_MINIMAX_API_BASE = "https://api.minimax.io/v1"
_MINIMAX_ANTHROPIC_API_BASE = "https://api.minimax.io/anthropic"
_MINIMAX_CN_API_BASE = "https://api.minimaxi.com/v1"
_MINIMAX_CN_ANTHROPIC_API_BASE = "https://api.minimaxi.com/anthropic"


# --- Branded LLM adapters -------------------------------------------------


@pytest.mark.parametrize(
    "adapter",
    [MiniMaxLLMAdapter, NvidiaBuildLLMAdapter, OpenRouterLLMAdapter],
)
def test_branded_llm_adapter_is_registered(adapter: type) -> None:
    adapter_id = adapter.get_id()
    assert adapter_id in llm_adapters
    assert llm_adapters[adapter_id][Common.MODULE] is adapter


def test_nvidia_llm_prefixes_model_via_custom_openai() -> None:
    validated = NvidiaBuildLLMParameters.validate({"model": "some-model", "api_key": "k"})

    assert validated["model"] == "custom_openai/some-model"
    assert validated["api_base"] == _NVIDIA_BUILD_API_BASE


@pytest.mark.parametrize("model", ["MiniMax-M3", "MiniMax-M2.7"])
@pytest.mark.parametrize(
    ("api_base", "provider"),
    [
        (_MINIMAX_API_BASE, "minimax"),
        (_MINIMAX_CN_API_BASE, "minimax"),
        (_MINIMAX_ANTHROPIC_API_BASE, "anthropic"),
        (_MINIMAX_CN_ANTHROPIC_API_BASE, "anthropic"),
    ],
)
def test_minimax_llm_routes_by_api_protocol(
    model: str, api_base: str, provider: str
) -> None:
    from litellm import get_llm_provider

    validated = MiniMaxLLMParameters.validate(
        {"model": model, "api_key": "k", "api_base": api_base}
    )

    assert validated["model"] == f"{provider}/{model}"
    assert validated["api_base"] == api_base
    assert validated["cost_model"] == f"minimax/{model}"
    assert get_llm_provider(validated["model"])[1] == provider
    assert validated["allowed_openai_params"] == ["service_tier", "thinking"]


@pytest.mark.parametrize("api_base", [_MINIMAX_API_BASE, _MINIMAX_ANTHROPIC_API_BASE])
def test_minimax_model_prefix_is_idempotent(api_base: str) -> None:
    once = MiniMaxLLMParameters.validate(
        {"model": "MiniMax-M3", "api_key": "k", "api_base": api_base}
    )
    twice = MiniMaxLLMParameters.validate(dict(once))

    assert twice["model"] == once["model"]


def test_minimax_model_prefix_follows_changed_protocol() -> None:
    openai = MiniMaxLLMParameters.validate({"model": "MiniMax-M3", "api_key": "k"})
    anthropic = MiniMaxLLMParameters.validate(
        {**openai, "api_base": _MINIMAX_ANTHROPIC_API_BASE}
    )

    assert anthropic["model"] == "anthropic/MiniMax-M3"


@pytest.mark.parametrize("model", ["MiniMax-M3", "MiniMax-M2.7"])
def test_minimax_native_routing_resolves_usage_cost(model: str) -> None:
    from litellm import cost_per_token

    prompt_cost, completion_cost = cost_per_token(
        f"minimax/{model}", prompt_tokens=1, completion_tokens=1
    )

    assert prompt_cost > 0
    assert completion_cost > 0


@pytest.mark.parametrize(
    ("model", "context_window", "max_output_tokens", "supports_vision"),
    [
        ("MiniMax-M3", 1_000_000, 524_288, True),
        ("MiniMax-M2.7", 204_800, 204_800, False),
    ],
)
def test_minimax_model_metadata_matches_official_limits(
    model: str,
    context_window: int,
    max_output_tokens: int,
    supports_vision: bool,
) -> None:
    from litellm import get_max_tokens, get_model_info

    model_name = f"minimax/{model}"
    info = get_model_info(model_name)

    assert info["max_input_tokens"] == context_window
    assert info["max_output_tokens"] == max_output_tokens
    assert info["supports_vision"] is supports_vision
    assert get_max_tokens(model_name) == max_output_tokens


def test_minimax_m3_usage_cost_preserves_context_and_service_tiers() -> None:
    base_usage = {
        "prompt_tokens": 512_000,
        "completion_tokens": 1,
        "total_tokens": 512_001,
    }
    long_usage = {
        "prompt_tokens": 512_001,
        "completion_tokens": 1,
        "total_tokens": 512_002,
    }

    assert MiniMaxLLMAdapter.calculate_usage_cost(
        "minimax/MiniMax-M3", base_usage
    ) == pytest.approx(512_000 * 0.3e-6 + 1.2e-6)
    assert MiniMaxLLMAdapter.calculate_usage_cost(
        "minimax/MiniMax-M3", long_usage
    ) == pytest.approx(512_001 * 0.6e-6 + 2.4e-6)
    assert MiniMaxLLMAdapter.calculate_usage_cost(
        "minimax/MiniMax-M3", base_usage, "priority"
    ) == pytest.approx(512_000 * 0.45e-6 + 1.8e-6)
    assert MiniMaxLLMAdapter.calculate_usage_cost(
        "minimax/MiniMax-M3", long_usage, "priority"
    ) == pytest.approx(512_001 * 0.9e-6 + 3.6e-6)


def test_minimax_usage_cost_preserves_cache_rates() -> None:
    m3_cache_read = {
        "prompt_tokens": 10,
        "completion_tokens": 0,
        "total_tokens": 10,
        "prompt_tokens_details": {"cached_tokens": 10},
    }
    m27_cache_write = {
        "prompt_tokens": 10,
        "completion_tokens": 0,
        "total_tokens": 10,
        "cache_creation_input_tokens": 10,
    }

    assert MiniMaxLLMAdapter.calculate_usage_cost(
        "anthropic/MiniMax-M3", m3_cache_read, "priority"
    ) == pytest.approx(10 * 0.09e-6)
    assert MiniMaxLLMAdapter.calculate_usage_cost(
        "minimax/MiniMax-M2.7", m27_cache_write
    ) == pytest.approx(10 * 0.375e-6)
    assert MiniMaxLLMAdapter.calculate_usage_cost(
        "minimax/MiniMax-M2.7", m27_cache_write, "priority"
    ) == pytest.approx(10 * 0.5625e-6)


def test_minimax_registered_metadata_preserves_tiered_prices() -> None:
    from litellm import model_cost

    info = model_cost["minimax/MiniMax-M3"]

    assert info["input_cost_per_token_above_512k_tokens"] == pytest.approx(0.6e-6)
    assert info["output_cost_per_token_above_512k_tokens"] == pytest.approx(2.4e-6)
    assert info["input_cost_per_token_priority"] == pytest.approx(0.45e-6)
    assert info["output_cost_per_token_above_512k_tokens_priority"] == pytest.approx(
        3.6e-6
    )


def test_minimax_temperature_uses_official_default_and_range() -> None:
    validated = MiniMaxLLMParameters.validate({"model": "MiniMax-M3", "api_key": "k"})

    assert validated["temperature"] == pytest.approx(1)
    for temperature in (-0.1, 2.1):
        with pytest.raises(ValueError):
            MiniMaxLLMParameters.validate(
                {
                    "model": "MiniMax-M3",
                    "api_key": "k",
                    "temperature": temperature,
                }
            )


@pytest.mark.parametrize("service_tier", ["standard", "priority"])
def test_minimax_forwards_supported_service_tiers(service_tier: str) -> None:
    validated = MiniMaxLLMParameters.validate(
        {
            "model": "MiniMax-M3",
            "api_key": "k",
            "service_tier": service_tier,
        }
    )

    assert validated["service_tier"] == service_tier


def test_minimax_rejects_unknown_service_tier() -> None:
    with pytest.raises(ValueError, match="service_tier"):
        MiniMaxLLMParameters.validate(
            {
                "model": "MiniMax-M3",
                "api_key": "k",
                "service_tier": "unsupported",
            }
        )


def test_minimax_maps_thinking_toggle_to_native_parameter() -> None:
    enabled = MiniMaxLLMParameters.validate(
        {"model": "MiniMax-M3", "api_key": "k", "enable_thinking": True}
    )
    disabled = MiniMaxLLMParameters.validate(
        {"model": "MiniMax-M3", "api_key": "k", "enable_thinking": False}
    )

    assert enabled["thinking"] == {"type": "adaptive"}
    assert disabled["thinking"] == {"type": "disabled"}
    assert "enable_thinking" not in enabled


def test_minimax_m2_rejects_disabling_thinking() -> None:
    with pytest.raises(ValueError, match="does not support disabling thinking"):
        MiniMaxLLMParameters.validate(
            {"model": "MiniMax-M2.7", "api_key": "k", "enable_thinking": False}
        )


def test_openrouter_llm_routes_via_native_openrouter_provider() -> None:
    from litellm import get_llm_provider

    validated = OpenRouterLLMParameters.validate(
        {"model": "openai/gpt-4o", "api_key": "k"}
    )

    assert validated["model"] == "openrouter/openai/gpt-4o"
    assert validated["api_base"] == _OPENROUTER_API_BASE
    # Native routing is what lets LiteLLM resolve OpenRouter pricing.
    assert get_llm_provider(validated["model"])[1] == "openrouter"


def test_openrouter_model_prefix_is_idempotent() -> None:
    once = OpenRouterLLMParameters.validate({"model": "openai/gpt-4o", "api_key": "k"})
    twice = OpenRouterLLMParameters.validate(dict(once))

    assert twice["model"] == once["model"] == "openrouter/openai/gpt-4o"


def test_openrouter_forwards_reasoning_effort_only_when_enabled() -> None:
    on = OpenRouterLLMParameters.validate(
        {
            "model": "openai/gpt-5",
            "api_key": "k",
            "enable_reasoning": True,
            "reasoning_effort": "high",
        }
    )
    assert on["reasoning_effort"] == "high"
    # enable_reasoning is a UI-only toggle and must not leak to LiteLLM.
    assert "enable_reasoning" not in on
    # temperature dropped so OpenAI o-series (via OpenRouter) don't reject it.
    assert on["temperature"] is None

    off = OpenRouterLLMParameters.validate(
        {
            "model": "openai/gpt-4o",
            "api_key": "k",
            "enable_reasoning": False,
            "reasoning_effort": "high",
        }
    )
    assert off["reasoning_effort"] is None


def test_openrouter_reasoning_survives_revalidation() -> None:
    once = OpenRouterLLMParameters.validate(
        {
            "model": "openai/gpt-5",
            "api_key": "k",
            "enable_reasoning": True,
            "reasoning_effort": "high",
        }
    )
    assert once["reasoning_effort"] == "high"
    # Reloading a saved config (no enable_reasoning key) must keep reasoning on.
    twice = OpenRouterLLMParameters.validate(dict(once))
    assert twice["reasoning_effort"] == "high"
    assert twice["temperature"] is None


@pytest.mark.parametrize(
    ("params", "default_base"),
    [
        (MiniMaxLLMParameters, _MINIMAX_API_BASE),
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
    [MiniMaxLLMParameters, NvidiaBuildLLMParameters, OpenRouterLLMParameters],
)
def test_branded_llm_honours_api_base_override(params: type) -> None:
    validated = params.validate(
        {"model": "m", "api_key": "k", "api_base": "https://proxy.internal/v1"}
    )

    assert validated["api_base"] == "https://proxy.internal/v1"


@pytest.mark.parametrize(
    ("adapter", "default_base"),
    [
        (MiniMaxLLMAdapter, _MINIMAX_API_BASE),
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


def test_minimax_schema_covers_models_thinking_and_regions() -> None:
    schema = json.loads(MiniMaxLLMAdapter.get_json_schema())

    assert schema["properties"]["model"]["examples"] == [
        "MiniMax-M3",
        "MiniMax-M2.7",
    ]
    assert schema["properties"]["enable_thinking"]["default"] is True
    endpoint_description = schema["properties"]["api_base"]["description"]
    for endpoint in (
        _MINIMAX_API_BASE,
        _MINIMAX_ANTHROPIC_API_BASE,
        _MINIMAX_CN_API_BASE,
        _MINIMAX_CN_ANTHROPIC_API_BASE,
    ):
        assert endpoint in endpoint_description
    assert schema["properties"]["service_tier"]["enum"] == [
        "standard",
        "priority",
    ]
    assert "reasoning_effort" not in json.dumps(schema)


# --- Branded / generic embedding adapters ---------------------------------


def test_nvidia_embedding_registered_and_routes_via_nvidia_nim() -> None:
    adapter_id = NvidiaBuildEmbeddingAdapter.get_id()
    assert adapter_id in embedding_adapters

    validated = NvidiaBuildEmbeddingParameters.validate(
        {"model": "nvidia/nv-embedqa-e5-v5", "api_key": "k"}
    )
    assert validated["model"] == "nvidia_nim/nvidia/nv-embedqa-e5-v5"
    assert validated["api_base"] == _NVIDIA_BUILD_API_BASE


def test_nvidia_embedding_defaults_encoding_format_to_float() -> None:
    # NVIDIA rejects the null encoding_format LiteLLM sends when unset.
    validated = NvidiaBuildEmbeddingParameters.validate(
        {"model": "nvidia/nv-embedqa-e5-v5", "api_key": "k"}
    )
    assert validated["encoding_format"] == "float"


def test_compatible_embedding_defaults_encoding_format_to_float() -> None:
    validated = OpenAICompatibleEmbeddingParameters.validate(
        {"model": "BAAI/bge-m3", "api_base": "https://gw.example/v1"}
    )
    assert validated["encoding_format"] == "float"


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


def test_compatible_embedding_blank_api_key_uses_placeholder() -> None:
    # Keyless gateways still need a non-empty key or the OpenAI SDK rejects it.
    validated = OpenAICompatibleEmbeddingParameters.validate(
        {"model": "m", "api_base": "https://gw.example/v1", "api_key": "  "}
    )
    assert isinstance(validated["api_key"], str)
    assert validated["api_key"].strip()


def test_compatible_embedding_requires_api_base() -> None:
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        OpenAICompatibleEmbeddingParameters.validate({"model": "m"})


def test_compatible_embedding_schema_loadable() -> None:
    schema = json.loads(OpenAICompatibleEmbeddingAdapter.get_json_schema())
    assert schema["title"] == "OpenAI Compatible Embedding"
    assert "api_base" in schema["required"]
    assert "model" in schema["required"]


@pytest.mark.parametrize(
    "adapter",
    [NvidiaBuildEmbeddingAdapter, OpenAICompatibleEmbeddingAdapter],
)
def test_embedding_schema_drops_embed_batch_size(adapter: type) -> None:
    # embed_batch_size is an inert llama-index hint; it must not be shown.
    schema = json.loads(adapter.get_json_schema())
    assert "embed_batch_size" not in schema["properties"]


def test_embedding_strips_embed_batch_size_before_litellm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Non-API fields must not reach the provider; encoding_format must be sent.
    import unstract.sdk1.embedding as emb_mod

    captured: dict = {}

    def fake_embedding(model: str, input: list, **kwargs: object) -> dict:  # noqa: A002
        captured["model"] = model
        captured.update(kwargs)
        return {"data": [{"embedding": [0.0, 1.0, 2.0]}]}

    monkeypatch.setattr(emb_mod.litellm, "embedding", fake_embedding)

    emb_mod.Embedding(
        adapter_id=NvidiaBuildEmbeddingAdapter.get_id(),
        adapter_metadata={
            "adapter_name": "n",
            "model": "nvidia/nv-embedqa-e5-v5",
            "api_key": "k",
            "embed_batch_size": 10,
        },
    )

    assert "embed_batch_size" not in captured
    assert captured["encoding_format"] == "float"
    assert captured["model"] == "nvidia_nim/nvidia/nv-embedqa-e5-v5"
    # Query path must send input_type for asymmetric models.
    assert captured["input_type"] == "query"


def _patch_capture_embedding(monkeypatch: pytest.MonkeyPatch) -> dict:
    import unstract.sdk1.embedding as emb_mod

    captured: dict = {}

    def fake_embedding(model: str, input: list, **kwargs: object) -> dict:  # noqa: A002
        captured["model"] = model
        captured.update(kwargs)
        return {"data": [{"embedding": [0.0, 1.0]}] * len(input)}

    monkeypatch.setattr(emb_mod.litellm, "embedding", fake_embedding)
    return captured


def test_nvidia_embedding_batch_sends_passage_input_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import unstract.sdk1.embedding as emb_mod

    captured = _patch_capture_embedding(monkeypatch)
    emb = emb_mod.Embedding(
        adapter_id=NvidiaBuildEmbeddingAdapter.get_id(),
        adapter_metadata={"model": "nvidia/nv-embedqa-e5-v5", "api_key": "k"},
    )
    emb.get_embeddings(["a", "b"])
    assert captured["input_type"] == "passage"


def test_compatible_embedding_omits_input_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # input_type is NVIDIA-only; non-nvidia_nim models must not receive it.
    import unstract.sdk1.embedding as emb_mod

    captured = _patch_capture_embedding(monkeypatch)
    emb_mod.Embedding(
        adapter_id=OpenAICompatibleEmbeddingAdapter.get_id(),
        adapter_metadata={
            "model": "BAAI/bge-m3",
            "api_base": "https://gw.example/v1",
            "api_key": "k",
        },
    )
    assert "input_type" not in captured
    assert captured["model"] == "openai/BAAI/bge-m3"
