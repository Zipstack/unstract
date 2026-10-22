"""Tests for resolving a provider/model to its vision image limits.

Resolution must key on the adapter provider (with the Bedrock Mantle
exception), match overrides first-match-wins on the bare model id and the
cost model, inherit across providers for OpenRouter slugs, and never
depend on which litellm cost map the process happened to load.
"""

import dataclasses

import pytest
from _pytest.monkeypatch import MonkeyPatch
from unstract.sdk1.exceptions import SdkError
from unstract.sdk1.llm import LLM
from unstract.sdk1.utils.image_limits import (
    ImageRequestLimits,
    local_max_input_tokens,
    provider_key,
    resolve_image_limits,
)
from unstract.sdk1.utils.image_limits import resolve as resolve_mod

AZURE_ID = "azureopenai|592d84b9-fe03-4102-a17e-6b391f32850b"
BEDROCK_ID = "bedrock|8d18571f-5e96-4505-bd28-ad0379c64064"
MINIMAX_ID = "minimax|4f0e4241-2430-4921-81bf-8b2c6040d8d2"
OLLAMA_ID = "ollama|4b8bd31a-ce42-48d4-9d69-f29c12e0f276"
NVIDIA_ID = "nvidiabuild|240d142d-68dd-4b6f-9716-80afd5c661cc"
COMPAT_ID = "openaicompatible|b6d10f33-2c41-49fc-a8c2-58d2b247fc09"


class TestProviderKey:
    def test_adapter_provider_is_the_key(self) -> None:
        assert provider_key("anthropic", "anthropic/claude-sonnet-4-5") == "anthropic"
        assert provider_key("ollama", "ollama_chat/llava") == "ollama"
        assert provider_key("nvidia_build", "custom_openai/llama") == "nvidia_build"

    def test_bedrock_mantle_route_is_keyed_separately(self) -> None:
        assert provider_key("bedrock", "bedrock/anthropic.claude-x") == "bedrock"
        assert provider_key("bedrock", "bedrock_mantle/openai.gpt-5.6-terra") == (
            "bedrock_mantle"
        )

    def test_minimax_is_never_keyed_by_its_litellm_prefix(self) -> None:
        assert provider_key("minimax", "anthropic/MiniMax-M3") == "minimax"


class TestResolution:
    @pytest.mark.parametrize(
        ("provider", "model", "cost_model", "expected"),
        [
            ("azure", "azure/my-dep", "azure/gpt-4o", 50),
            ("azure", "azure/my-dep", None, 50),
            ("bedrock", "bedrock/us.amazon.nova-2-lite-v1:0", None, 5),
            ("bedrock", "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0", None, 20),
            ("bedrock", "bedrock_mantle/openai.gpt-5.6-terra", None, 100),
            ("anthropic", "anthropic/claude-sonnet-4-5", None, 100),
            ("anthropic", "anthropic/claude-sonnet-4-0", None, 100),
            ("anthropic", "anthropic/claude-opus-4-7", None, 600),
            ("openai", "openai/gpt-5.6", None, 1500),
            ("gemini", "gemini/gemini-3-flash", None, 3600),
            ("mistral", "mistral/pixtral-large-latest", None, 8),
            ("vertex_ai", "vertex_ai/claude-haiku-4-5@20251001", None, 100),
            ("vertex_ai", "vertex_ai/gemini-3.1-pro", None, 3000),
        ],
    )
    def test_max_images_table(
        self, provider: str, model: str, cost_model: str | None, expected: int
    ) -> None:
        limits = resolve_image_limits(provider, model, cost_model=cost_model)
        assert limits.max_images_per_request.value == expected

    def test_azure_cost_model_hits_the_documented_override(self) -> None:
        with_cost = resolve_image_limits(
            "azure", "azure/my-dep", cost_model="azure/gpt-4o"
        )
        without = resolve_image_limits("azure", "azure/my-dep")
        assert with_cost.max_images_per_request.confidence == "verified"
        assert without.max_images_per_request.confidence == "unverified"
        assert with_cost.matched_override and "GPT-4o" in with_cost.matched_override
        assert without.matched_override is None

    def test_mantle_gemma_has_its_own_request_byte_limit(self) -> None:
        limits = resolve_image_limits("bedrock", "bedrock_mantle/google.gemma-4-31b")
        assert limits.max_request_bytes.value == 3_500_000
        # Count is undocumented on Mantle -> top-level default, enforced
        # (hosted provider), not advisory.
        assert limits.max_images_per_request.value == 20
        assert limits.max_images_per_request.from_default is True
        assert limits.max_images_per_request.advisory is False

    def test_bedrock_converse_route_keeps_the_conservative_cap(self) -> None:
        # Some bedrock/ ids route via Invoke; 20 stays as the conservative cap.
        limits = resolve_image_limits(
            "bedrock", "bedrock/anthropic.claude-mythos-preview"
        )
        assert limits.max_images_per_request.value == 20

    def test_minimax_on_anthropic_endpoint_keeps_minimax_limits(self) -> None:
        limits = resolve_image_limits("minimax", "anthropic/MiniMax-M3")
        assert limits.provider_key == "minimax"
        assert limits.max_request_bytes.value == 64_000_000

    def test_anthropic_split_does_not_come_from_litellm(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        # litellm 1.104 lists claude-sonnet-4-5 as a 1M model; Anthropic says
        # 200k. The 100/600 split must come from our own list regardless.
        monkeypatch.setattr(
            resolve_mod.litellm,
            "model_cost",
            {
                "claude-sonnet-4-5": {
                    "max_input_tokens": 1_000_000,
                    "supports_vision": True,
                }
            },
        )
        limits = resolve_image_limits("anthropic", "anthropic/claude-sonnet-4-5")
        assert limits.max_images_per_request.value == 100

    def test_openrouter_inherits_the_family_limits(self) -> None:
        limits = resolve_image_limits(
            "openrouter", "openrouter/anthropic/claude-haiku-4-5"
        )
        assert limits.inherited_from == "anthropic"
        assert limits.max_images_per_request.value == 100  # 200k override applied
        assert limits.max_request_bytes.value == 32_000_000
        assert limits.max_images_per_request.advisory is False

    def test_openrouter_unknown_upstream_is_advisory_default(self) -> None:
        limits = resolve_image_limits("openrouter", "openrouter/qwen/qwen3-vl")
        assert limits.inherited_from is None
        assert limits.max_images_per_request.value == 20
        assert limits.max_images_per_request.from_default is True
        assert limits.max_images_per_request.advisory is True
        assert limits.max_request_bytes.advisory is True

    def test_pass_through_providers_get_advisory_defaults(self) -> None:
        for provider, model in (
            ("ollama", "ollama_chat/llava"),
            ("custom_openai", "custom_openai/qwen2.5-vl"),
            ("nvidia_build", "custom_openai/meta/llama-3.2-90b-vision-instruct"),
        ):
            limits = resolve_image_limits(provider, model)
            assert limits.provider_kind == "pass_through", provider
            assert limits.max_images_per_request.value == 20, provider
            assert limits.max_images_per_request.advisory is True, provider

    def test_unknown_provider_falls_back_to_default_entry(self) -> None:
        limits = resolve_image_limits("not-a-provider", "x/y")
        assert limits.is_default_provider is True
        assert limits.max_images_per_request.value == 20
        assert limits.provider_label == "not-a-provider"

    def test_per_image_nulls_mean_skip(self) -> None:
        limits = resolve_image_limits("openai", "openai/gpt-5.6")
        assert limits.max_image_bytes.value is None
        assert limits.max_image_px.value is None
        assert limits.max_image_patches.value == 30_000

    def test_provenance_is_carried(self) -> None:
        limits = resolve_image_limits("bedrock", "bedrock/amazon.nova-pro-v1:0")
        count = limits.max_images_per_request
        assert count.confidence == "verified"
        assert any(
            url.startswith("https://docs.aws.amazon.com") for url in count.source_urls
        )
        assert count.verified_on == "2026-10-09"

    def test_base64_counted_defaults_to_true(self) -> None:
        # Llama on Bedrock matches no override, so the provider defaults apply.
        bedrock = resolve_image_limits(
            "bedrock", "bedrock/meta.llama3-2-90b-instruct-v1:0"
        )
        assert bedrock.max_image_bytes.base64_counted is False  # explicit in data
        assert bedrock.max_request_bytes.base64_counted is True  # absent -> True

    def test_extra_model_ids_are_matched_last(self) -> None:
        arn = "bedrock/arn:aws:bedrock:us-east-1:1:application-inference-profile/abc"
        limits = resolve_image_limits(
            "bedrock", arn, extra_model_ids=["us.amazon.nova-2-lite-v1:0"]
        )
        assert limits.max_images_per_request.value == 5


class TestCostMapIndependence:
    """Resolution keys on the VALIDATED model string, never on litellm's map.

    Production litellm loads the remote cost map while the tests pin the
    bundled one, so Mantle membership can differ between them. Whatever the
    adapter validated to is what we resolve on.
    """

    class _Exploding(dict):
        def __contains__(self, item: object) -> bool:
            raise AssertionError("resolution consulted litellm.model_cost")

        def get(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("resolution consulted litellm.model_cost")

    def test_resolution_never_touches_the_cost_map(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setattr(resolve_mod.litellm, "model_cost", self._Exploding())
        a = resolve_image_limits("bedrock", "bedrock_mantle/anthropic.claude-opus-5-5")
        b = resolve_image_limits("bedrock", "bedrock/anthropic.claude-opus-5-5")
        assert a.provider_key == "bedrock_mantle"
        assert b.provider_key == "bedrock"

    def test_same_validated_string_resolves_identically_under_either_map(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        model = "bedrock_mantle/anthropic.claude-opus-5-5"
        monkeypatch.setattr(resolve_mod.litellm, "model_cost", {})
        without = resolve_image_limits("bedrock", model)
        monkeypatch.setattr(
            resolve_mod.litellm, "model_cost", {model: {"supports_vision": True}}
        )
        with_key = resolve_image_limits("bedrock", model)
        assert without == with_key


class TestLocalMaxInputTokens:
    def test_reads_the_local_registry_only(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(
            resolve_mod.litellm, "model_cost", {"gpt-5.6": {"max_input_tokens": 400_000}}
        )
        monkeypatch.setattr(
            resolve_mod.litellm,
            "get_model_info",
            lambda *a, **k: pytest.fail("network lookup"),
        )
        assert local_max_input_tokens("openai/gpt-5.6") == 400_000

    def test_prefers_cost_model_over_deployment_name(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            resolve_mod.litellm,
            "model_cost",
            {"azure/gpt-4o": {"max_input_tokens": 128_000}},
        )
        assert (
            local_max_input_tokens("azure/my-dep", cost_model="azure/gpt-4o") == 128_000
        )

    def test_unknown_is_none_never_a_fallback_number(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setattr(resolve_mod.litellm, "model_cost", {})
        assert local_max_input_tokens("ollama_chat/llava") is None


def _for_adapter(adapter_id: str, metadata: dict) -> ImageRequestLimits:
    """Limits from an adapter id + stored metadata (the backend's entry point)."""
    return LLM.image_input_limits_for(adapter_id, metadata, refresh_table=False)[0]


class TestResolveForAdapter:
    def test_azure_uses_cost_model_for_matching(self) -> None:
        limits = _for_adapter(
            AZURE_ID,
            {
                "deployment_name": "my-dep",
                "model": "gpt-4o",
                "api_base": "https://x.openai.azure.com",
                "api_key": "k",
            },
        )
        assert limits.provider_key == "azure"
        assert limits.max_images_per_request.confidence == "verified"

    def test_bedrock_mantle_detected_from_validated_prefix(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        import litellm

        monkeypatch.setattr(
            litellm, "model_cost", {"bedrock_mantle/openai.gpt-5.6-terra": {}}
        )
        limits = _for_adapter(
            BEDROCK_ID, {"model": "openai.gpt-5.6-terra", "aws_region_name": "us-east-1"}
        )
        assert limits.provider_key == "bedrock_mantle"
        assert limits.max_images_per_request.value == 100

    def test_minimax_anthropic_base_keeps_minimax(self) -> None:
        limits = _for_adapter(
            MINIMAX_ID,
            {
                "model": "MiniMax-M3",
                "api_key": "k",
                "api_base": "https://api.minimax.io/anthropic",
            },
        )
        assert limits.provider_key == "minimax"

    def test_pass_through_adapters(self) -> None:
        ollama = _for_adapter(
            OLLAMA_ID, {"model": "llava", "api_base": "http://localhost:11434"}
        )
        nvidia = _for_adapter(NVIDIA_ID, {"model": "x/y", "api_key": "k"})
        compat = _for_adapter(
            COMPAT_ID, {"model": "y", "api_base": "http://vllm:8000/v1"}
        )
        assert ollama.provider_key == "ollama"
        assert nvidia.provider_key == "nvidia_build"
        assert compat.provider_key == "custom_openai"
        assert all(x.max_images_per_request.advisory for x in (ollama, nvidia, compat))

    def test_unknown_adapter_id_raises(self) -> None:
        with pytest.raises(SdkError):
            _for_adapter("nope|123", {"model": "x"})

    def test_result_is_a_frozen_dataclass(self) -> None:
        limits = resolve_image_limits("openai", "openai/gpt-5.6")
        assert isinstance(limits, ImageRequestLimits)
        with pytest.raises(dataclasses.FrozenInstanceError):
            limits.provider_key = "x"  # type: ignore[misc]


class TestClaude200kRuleAcrossRoutes:
    """The 200k-context Claude rule (100 images) is applied on every route.

    OpenRouter's real slugs use a dot between version digits
    (``anthropic/claude-sonnet-4.5``) and Mantle uses ``anthropic.<id>``;
    both used to resolve to 600 images.
    """

    @pytest.mark.parametrize(
        "slug",
        [
            "openrouter/anthropic/claude-sonnet-4.5",
            "openrouter/anthropic/claude-haiku-4.5",
            "openrouter/anthropic/claude-opus-4.1",
            "openrouter/anthropic/claude-opus-4.5",
        ],
    )
    def test_openrouter_dotted_slugs_get_100(self, slug: str) -> None:
        limits = resolve_image_limits("openrouter", slug)
        assert limits.inherited_from == "anthropic"
        assert limits.max_images_per_request.value == 100

    @pytest.mark.parametrize(
        "slug",
        [
            "openrouter/anthropic/claude-sonnet-4.6",
            "openrouter/anthropic/claude-opus-4.7",
        ],
    )
    def test_openrouter_1m_models_keep_600(self, slug: str) -> None:
        assert (
            resolve_image_limits("openrouter", slug).max_images_per_request.value == 600
        )

    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("bedrock_mantle/anthropic.claude-sonnet-4-5-20250929-v1:0", 100),
            ("bedrock_mantle/anthropic.claude-haiku-4-5", 100),
            ("bedrock_mantle/anthropic.claude-opus-4-1", 100),
            ("bedrock_mantle/anthropic.claude-sonnet-4-6", 600),
            ("bedrock_mantle/anthropic.claude-opus-5-5", 600),
        ],
    )
    def test_mantle_applies_the_same_split(self, model: str, expected: int) -> None:
        limits = resolve_image_limits("bedrock", model)
        assert limits.provider_key == "bedrock_mantle"
        assert limits.max_images_per_request.value == expected


class TestClaudeHighResTokens:
    """Claude 4.7+ is Anthropic's high-resolution image tier (~2,850/page)."""

    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            ("anthropic", "anthropic/claude-opus-4-7"),
            ("anthropic", "anthropic/claude-opus-5-5"),
            ("vertex_ai", "vertex_ai/claude-opus-4-8"),
            ("azure_ai", "azure_ai/claude-sonnet-5"),
            ("bedrock", "bedrock_mantle/anthropic.claude-opus-5-5"),
            ("openrouter", "openrouter/anthropic/claude-opus-4.7"),
        ],
    )
    def test_high_res_models_use_2850(self, provider: str, model: str) -> None:
        limits = resolve_image_limits(provider, model)
        assert limits.tokens_per_image.value == 2850
        assert limits.tokens_per_image.from_default is False
        assert limits.max_images_per_request.value == 600

    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            ("anthropic", "anthropic/claude-sonnet-4-5"),
            ("anthropic", "anthropic/claude-sonnet-4-6"),
            ("vertex_ai", "vertex_ai/claude-haiku-4-5@20251001"),
        ],
    )
    def test_standard_tier_models_keep_the_default(
        self, provider: str, model: str
    ) -> None:
        limits = resolve_image_limits(provider, model)
        assert limits.tokens_per_image.value == 1500
        assert limits.tokens_per_image.from_default is True

    def test_vertex_high_res_keeps_the_vertex_claude_limits(self) -> None:
        limits = resolve_image_limits("vertex_ai", "vertex_ai/claude-opus-4-8")
        assert limits.max_request_bytes.value == 30_000_000
        assert limits.max_image_bytes.value == 5_000_000
        assert limits.many_images_threshold.value == 20
