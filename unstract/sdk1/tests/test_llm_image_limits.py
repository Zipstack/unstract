"""Tests for the ``LLM`` accessors that expose image-request limits."""

import pytest
from _pytest.monkeypatch import MonkeyPatch
from unstract.sdk1.llm import LLM
from unstract.sdk1.utils.image_limits import ImageRequestLimits
from unstract.sdk1.utils.image_limits import resolve as resolve_mod

AZURE_ID = "azureopenai|592d84b9-fe03-4102-a17e-6b391f32850b"
BEDROCK_ID = "bedrock|8d18571f-5e96-4505-bd28-ad0379c64064"
MINIMAX_ID = "minimax|4f0e4241-2430-4921-81bf-8b2c6040d8d2"
OPENAI_ID = "openai|502ecf49-e47c-445c-9907-6d4b90c5cd17"

AZURE_META = {
    "deployment_name": "my-dep",
    "model": "gpt-4o",
    "api_base": "https://x.openai.azure.com",
    "api_key": "k",
}


class TestGetImageRequestLimits:
    def test_uses_adapter_provider_and_cost_model(self) -> None:
        llm = LLM(adapter_id=AZURE_ID, adapter_metadata=dict(AZURE_META))
        limits = llm.get_image_request_limits()
        assert isinstance(limits, ImageRequestLimits)
        assert limits.provider_key == "azure"
        # The real model (cost_model), not the deployment name, matched.
        assert limits.max_images_per_request.confidence == "verified"

    def test_bedrock_inference_profile_uses_model_id(self) -> None:
        llm = LLM(
            adapter_id=BEDROCK_ID,
            adapter_metadata={
                "model": "arn:aws:bedrock:us-east-1:1:application-inference-profile/abc",
                "model_id": "us.amazon.nova-2-lite-v1:0",
                "aws_region_name": "us-east-1",
            },
        )
        assert llm.get_image_request_limits().max_images_per_request.value == 5

    def test_minimax_anthropic_endpoint(self) -> None:
        llm = LLM(
            adapter_id=MINIMAX_ID,
            adapter_metadata={
                "model": "MiniMax-M3",
                "api_key": "k",
                "api_base": "https://api.minimax.io/anthropic",
            },
        )
        assert llm.get_image_request_limits().provider_key == "minimax"


class TestGetImageInputTokenBudget:
    def test_adapter_context_window_is_kept(self) -> None:
        # MiniMax's validator sets context_window (1M for M3); LLM used to
        # discard it.
        llm = LLM(
            adapter_id=MINIMAX_ID,
            adapter_metadata={"model": "MiniMax-M3", "api_key": "k"},
        )
        assert llm.get_image_input_token_budget() == 1_000_000

    def test_falls_back_to_the_local_registry(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(
            resolve_mod.litellm,
            "model_cost",
            {"azure/gpt-4o": {"max_input_tokens": 128_000}},
        )
        llm = LLM(adapter_id=AZURE_ID, adapter_metadata=dict(AZURE_META))
        assert llm.get_image_input_token_budget() == 128_000

    def test_unknown_is_none(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(resolve_mod.litellm, "model_cost", {})
        llm = LLM(
            adapter_id=OPENAI_ID,
            adapter_metadata={
                "model": "gpt-5.6",
                "api_key": "k",
                "api_base": "https://api.openai.com/v1",
            },
        )
        assert llm.get_image_input_token_budget() is None

    def test_never_calls_get_model_info(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(resolve_mod.litellm, "model_cost", {})
        monkeypatch.setattr(
            resolve_mod.litellm, "get_model_info", lambda *a, **k: pytest.fail("network")
        )
        llm = LLM(
            adapter_id=OPENAI_ID,
            adapter_metadata={
                "model": "gpt-5.6",
                "api_key": "k",
                "api_base": "https://api.openai.com/v1",
            },
        )
        llm.get_image_input_token_budget()


class TestImageInputLimitsFor:
    def test_classmethod_matches_the_instance(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(
            resolve_mod.litellm,
            "model_cost",
            {"azure/gpt-4o": {"max_input_tokens": 128_000}},
        )
        limits, tokens = LLM.image_input_limits_for(AZURE_ID, AZURE_META)
        llm = LLM(adapter_id=AZURE_ID, adapter_metadata=dict(AZURE_META))
        assert limits == llm.get_image_request_limits()
        assert tokens == llm.get_image_input_token_budget() == 128_000

    def test_does_not_mutate_the_metadata(self) -> None:
        meta = dict(AZURE_META)
        LLM.image_input_limits_for(AZURE_ID, meta)
        assert meta == AZURE_META
