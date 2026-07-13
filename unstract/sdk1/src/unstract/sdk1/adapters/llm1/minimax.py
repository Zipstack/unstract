from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from litellm import register_model
from unstract.sdk1.adapters.base1 import BaseAdapter, MiniMaxLLMParameters
from unstract.sdk1.adapters.enums import AdapterTypes

DESCRIPTION = (
    "Adapter for MiniMax's OpenAI- and Anthropic-compatible APIs. "
    "Supply a model name and your MiniMax API key; the endpoint is preconfigured."
)

_MILLION = 1_000_000
_M3_LONG_CONTEXT_THRESHOLD = 512_000
_PRICING_SOURCE = "https://platform.minimax.io/docs/guides/pricing-paygo"


@dataclass(frozen=True)
class _TokenRates:
    input: float
    output: float
    cache_read: float
    cache_write: float | None = None


@dataclass(frozen=True)
class _ModelSpec:
    context_window: int
    max_output_tokens: int
    standard: _TokenRates
    priority: _TokenRates
    supports_vision: bool
    long_standard: _TokenRates | None = None
    long_priority: _TokenRates | None = None


def _rate(usd_per_million_tokens: float) -> float:
    return usd_per_million_tokens / _MILLION


_MODEL_SPECS = {
    "MiniMax-M3": _ModelSpec(
        context_window=1_000_000,
        max_output_tokens=524_288,
        standard=_TokenRates(_rate(0.3), _rate(1.2), _rate(0.06)),
        priority=_TokenRates(_rate(0.45), _rate(1.8), _rate(0.09)),
        supports_vision=True,
        long_standard=_TokenRates(_rate(0.6), _rate(2.4), _rate(0.12)),
        long_priority=_TokenRates(_rate(0.9), _rate(3.6), _rate(0.18)),
    ),
    "MiniMax-M2.7": _ModelSpec(
        context_window=204_800,
        max_output_tokens=204_800,
        standard=_TokenRates(_rate(0.3), _rate(1.2), _rate(0.06), _rate(0.375)),
        priority=_TokenRates(_rate(0.45), _rate(1.8), _rate(0.09), _rate(0.5625)),
        supports_vision=False,
    ),
}


def _model_info(provider: str, spec: _ModelSpec) -> dict[str, Any]:
    info: dict[str, Any] = {
        "litellm_provider": provider,
        "mode": "chat",
        "max_input_tokens": spec.context_window,
        "max_output_tokens": spec.max_output_tokens,
        "input_cost_per_token": spec.standard.input,
        "output_cost_per_token": spec.standard.output,
        "cache_read_input_token_cost": spec.standard.cache_read,
        "input_cost_per_token_priority": spec.priority.input,
        "output_cost_per_token_priority": spec.priority.output,
        "cache_read_input_token_cost_priority": spec.priority.cache_read,
        "source": _PRICING_SOURCE,
        "supports_function_calling": True,
        "supports_prompt_caching": True,
        "supports_reasoning": True,
        "supports_service_tier": True,
        "supports_system_messages": True,
        "supports_tool_choice": True,
        "supports_vision": spec.supports_vision,
    }
    if spec.standard.cache_write is not None:
        info["cache_creation_input_token_cost"] = spec.standard.cache_write
    if spec.priority.cache_write is not None:
        info["cache_creation_input_token_cost_priority"] = spec.priority.cache_write
    if spec.long_standard is not None and spec.long_priority is not None:
        info.update(
            {
                "input_cost_per_token_above_512k_tokens": spec.long_standard.input,
                "output_cost_per_token_above_512k_tokens": spec.long_standard.output,
                "cache_read_input_token_cost_above_512k_tokens": (
                    spec.long_standard.cache_read
                ),
                "input_cost_per_token_above_512k_tokens_priority": (
                    spec.long_priority.input
                ),
                "output_cost_per_token_above_512k_tokens_priority": (
                    spec.long_priority.output
                ),
                "cache_read_input_token_cost_above_512k_tokens_priority": (
                    spec.long_priority.cache_read
                ),
            }
        )
    return info


register_model(
    {
        f"{provider}/{model_id}": _model_info(provider, spec)
        for model_id, spec in _MODEL_SPECS.items()
        for provider in ("minimax", "anthropic")
    }
)


def _usage_value(usage: Mapping[str, Any], key: str) -> int:
    value = usage.get(key, 0)
    return int(value or 0)


def _detail_value(details: object, key: str) -> int:
    if isinstance(details, Mapping):
        value = details.get(key, 0)
    else:
        value = getattr(details, key, 0)
    return int(value or 0)


class MiniMaxLLMAdapter(MiniMaxLLMParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "minimax|4f0e4241-2430-4921-81bf-8b2c6040d8d2"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "MiniMax",
            "version": "1.0.0",
            "adapter": MiniMaxLLMAdapter,
            "description": DESCRIPTION,
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "MiniMax"

    @staticmethod
    def get_description() -> str:
        return DESCRIPTION

    @staticmethod
    def get_provider() -> str:
        return "minimax"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/MiniMax.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM

    @staticmethod
    def calculate_usage_cost(
        model: str,
        usage: Mapping[str, Any],
        service_tier: str | None = None,
    ) -> float | None:
        model_id = model.rsplit("/", 1)[-1]
        spec = _MODEL_SPECS.get(model_id)
        if spec is None:
            return None

        tier = service_tier or "standard"
        rates = spec.priority if tier == "priority" else spec.standard
        prompt_tokens = _usage_value(usage, "prompt_tokens")
        if model_id == "MiniMax-M3" and prompt_tokens > _M3_LONG_CONTEXT_THRESHOLD:
            long_rates = spec.long_priority if tier == "priority" else spec.long_standard
            if long_rates is not None:
                rates = long_rates

        cache_read_tokens = _usage_value(usage, "cache_read_input_tokens")
        cache_write_tokens = _usage_value(usage, "cache_creation_input_tokens")
        prompt_details = usage.get("prompt_tokens_details")
        if prompt_details is not None:
            cache_read_tokens = cache_read_tokens or _detail_value(
                prompt_details, "cached_tokens"
            )
            cache_write_tokens = cache_write_tokens or _detail_value(
                prompt_details, "cache_creation_tokens"
            )

        uncached_tokens = max(
            prompt_tokens - cache_read_tokens - cache_write_tokens,
            0,
        )
        cache_write_rate = rates.cache_write or 0
        input_cost = (
            uncached_tokens * rates.input
            + cache_read_tokens * rates.cache_read
            + cache_write_tokens * cache_write_rate
        )
        output_cost = _usage_value(usage, "completion_tokens") * rates.output
        return input_cost + output_cost
