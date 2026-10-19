"""Validate MiniMax metadata through the real LiteLLM HTTP request builders."""

import json
from typing import Any
from unittest.mock import patch

import httpx
import litellm
import pytest

import unstract.sdk1.llm  # noqa: F401 - applies production LiteLLM settings
from unstract.sdk1.adapters.base1 import MiniMaxLLMParameters


@pytest.mark.parametrize("host", ["api.minimax.io", "api.minimaxi.com"])
@pytest.mark.parametrize("protocol", ["v1", "anthropic"])
@pytest.mark.parametrize("model", ["MiniMax-M3.1-Flash", "MiniMax-M3"])
def test_minimax_wire_contract(host: str, protocol: str, model: str) -> None:
    requests: list[dict[str, Any]] = []

    def capture(
        self: Any,  # noqa: ANN401
        url: str,
        data: Any = None,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> httpx.Response:
        body = json.loads(data) if isinstance(data, str | bytes) else data
        requests.append({"url": url, "body": body})
        if protocol == "anthropic":
            payload = {
                "id": "msg-test",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        else:
            payload = {
                "id": "chat-test",
                "object": "chat.completion",
                "created": 1,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    metadata = MiniMaxLLMParameters.validate(
        {
            "model": model,
            "api_key": "test-key",
            "api_base": f"https://{host}/{protocol}",
            "max_tokens": 32,
            "service_tier": "standard",
            "enable_thinking": model == "MiniMax-M3.1-Flash",
        }
    )
    assert MiniMaxLLMParameters.validate(dict(metadata)) == metadata
    metadata.pop("cost_model", None)
    metadata.pop("context_window", None)
    with patch("litellm.llms.custom_httpx.http_handler.HTTPHandler.post", capture):
        result = litellm.completion(
            messages=[{"role": "user", "content": "hi"}], **metadata
        )
    assert result.choices[0].message.content == "ok"
    assert len(requests) == 1
    request = requests[0]
    endpoint = (
        "anthropic/v1/messages" if protocol == "anthropic" else "v1/chat/completions"
    )
    assert request["url"] == f"https://{host}/{endpoint}"
    body = request["body"]
    assert body["model"] == model
    assert body.get("reasoning_effort") is None
    assert body.get("output_config") is None
    assert body.get("reasoning_split") is not False
    if model == "MiniMax-M3.1-Flash":
        assert "service_tier" not in body
        assert body["thinking"] == {"type": "adaptive"}
    else:
        assert body["service_tier"] == "standard"
        assert body["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize(
    "setting",
    [
        {"enable_thinking": False},
        {"thinking": {"type": "disabled"}},
        {"thinking": {"type": "enabled", "budget_tokens": 1024}},
    ],
)
def test_flash_rejects_unsupported_thinking(setting: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="requires adaptive thinking"):
        MiniMaxLLMParameters.validate(
            {"model": "MiniMax-M3.1-Flash", "api_key": "test-key", **setting}
        )


@pytest.mark.parametrize("service_tier", [None, "standard", "priority"])
def test_flash_defaults_survive_saved_configuration(service_tier: str | None) -> None:
    validated = MiniMaxLLMParameters.validate(
        {
            "model": "MiniMax-M3.1-Flash",
            "api_key": "test-key",
            "service_tier": service_tier,
        }
    )
    assert validated["thinking"] == {"type": "adaptive"}
    assert "service_tier" not in validated
    assert validated["context_window"] == 1_000_000
    assert MiniMaxLLMParameters.validate(dict(validated)) == validated


@pytest.mark.parametrize("model", ["custom-model", "MiniMax-M3.1-Flash-custom"])
def test_flash_rules_do_not_restrict_custom_models(model: str) -> None:
    validated = MiniMaxLLMParameters.validate(
        {
            "model": model,
            "api_key": "test-key",
            "enable_thinking": False,
            "service_tier": "priority",
        }
    )
    assert validated["thinking"] == {"type": "disabled"}
    assert validated["service_tier"] == "priority"
