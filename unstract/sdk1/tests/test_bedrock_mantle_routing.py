"""End-to-end wire tests for AWS Bedrock routing through LiteLLM.

The unit tests in ``test_bedrock_adapter.py`` assert the *shape* the adapter
produces. These assert what actually goes on the wire when that shape is handed
to ``litellm.completion()``: the URL, the signed Authorization header and the
request body. The HTTP transport is patched and the model registry is pinned
to the bundled copy in ``tests/conftest.py``, so no AWS credentials, network
access or spend are involved.

Why this matters: the two Bedrock endpoints differ in every one of those three
respects. Getting the provider prefix wrong is not a soft failure -- the request
lands on the wrong host with the wrong body schema.
"""

import json
import os
from typing import Any
from unittest.mock import patch

import httpx
import pytest

# Imported for its import-time side effect: it sets `litellm.drop_params`,
# which the Mantle path depends on (see `_complete`).
import unstract.sdk1.llm  # noqa: F401
from unstract.sdk1.adapters.base1 import AWSBedrockLLMParameters

# Placeholder credentials. SigV4 is a keyed hash over the request, so signing
# succeeds for any non-empty key material -- these never reach AWS because the
# HTTP transport is patched, and are deliberately low-entropy so no scanner
# mistakes them for a real credential.
_FAKE_SECRET = "not-a-real-aws-secret-access-key"  # noqa: S105
_FAKE_KEY_ID = "AKIAEXAMPLEKEY"

_BASE: dict[str, str] = {
    "region_name": "us-east-1",
    "aws_access_key_id": _FAKE_KEY_ID,
    "aws_secret_access_key": _FAKE_SECRET,
}

# Env vars LiteLLM consults for Bedrock/Mantle auth and region. Cleared so a
# developer's real shell config cannot change what the test observes.
_AMBIENT_VARS = (
    "BEDROCK_MANTLE_API_KEY",
    "BEDROCK_MANTLE_API_BASE",
    "BEDROCK_MANTLE_REGION",
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_REGION",
    "AWS_REGION_NAME",
    "AWS_DEFAULT_REGION",
)


@pytest.fixture(autouse=True)
def _isolated_litellm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip ambient AWS config and assert the registry pin actually took.

    The registry pin itself cannot live here: ``LITELLM_LOCAL_MODEL_COST_MAP``
    is read once when litellm is imported, which happens at collection time,
    so setting it from a fixture body is a no-op that silently leaves these
    tests reading the *network* registry. It is set at module scope in
    ``tests/conftest.py`` instead; the assertion below fails loudly if that
    ever stops taking effect rather than quietly reverting to the network.
    """
    assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP") == "True", (
        "Expected the bundled LiteLLM registry to be pinned in conftest.py; "
        "without it these routing assertions depend on a network fetch."
    )
    for var in _AMBIENT_VARS:
        monkeypatch.delenv(var, raising=False)


def _chat_completion_payload() -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _responses_payload() -> dict[str, Any]:
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": "test",
        "output": [
            {
                "type": "message",
                "id": "msg_test",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "ok", "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
    }


def _converse_payload() -> dict[str, Any]:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
    }


def _complete(metadata: dict[str, Any]) -> dict[str, Any]:
    """Run adapter validation + litellm.completion against a patched transport.

    Returns the single captured request: url, headers and decoded JSON body.
    """
    import litellm

    captured: list[dict[str, Any]] = []

    def _mock_post(
        self: Any,  # noqa: ANN401, ARG001
        url: str,
        data: Any = None,  # noqa: ANN401
        headers: dict[str, str] | None = None,
        **_kwargs: Any,  # noqa: ANN401
    ) -> httpx.Response:
        body = json.loads(data) if isinstance(data, str | bytes) else (data or {})
        captured.append({"url": url, "headers": headers or {}, "body": body})
        if "/responses" in url:
            payload = _responses_payload()
        elif "/converse" in url:
            payload = _converse_payload()
        else:
            payload = _chat_completion_payload()
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    completion_kwargs = AWSBedrockLLMParameters.validate(metadata)
    # Assert rather than set. The whole Mantle path is load-bearing on
    # `unstract.sdk1.llm` setting this globally: the adapter emits the
    # `BaseChatCompletionParameters` default `temperature=0.1` for a
    # non-reasoning call, and GPT-5.x rejects any temperature but 1 *before*
    # issuing the request. Setting the flag here instead would keep this suite
    # green through a refactor that dropped it, while every GPT-5.x Bedrock
    # completion broke in production.
    assert litellm.drop_params is True, (
        "unstract.sdk1.llm must set litellm.drop_params; without it GPT-5.x "
        "rejects the adapter's default temperature before any HTTP request."
    )

    with patch("litellm.llms.custom_httpx.http_handler.HTTPHandler.post", _mock_post):
        litellm.completion(
            messages=[{"role": "user", "content": "hi"}], **completion_kwargs
        )

    assert len(captured) == 1, f"expected exactly one request, got {len(captured)}"
    return captured[0]


def test_mantle_model_hits_mantle_endpoint_signed_with_access_keys() -> None:
    """GPT-5.6 Terra must reach bedrock-mantle over SigV4 with per-adapter keys.

    This is the regression the whole change exists for: routed as `bedrock/` it
    went to bedrock-runtime Converse instead and failed.
    """
    req = _complete({**_BASE, "model": "openai.gpt-5.6-terra", "max_tokens": 64})

    assert req["url"] == ("https://bedrock-mantle.us-east-1.api.aws/openai/v1/responses")
    authorization = req["headers"]["Authorization"]
    assert authorization.startswith("AWS4-HMAC-SHA256")
    assert f"Credential={_FAKE_KEY_ID}/" in authorization
    # SigV4 credential scope must name the signing region and the bedrock service.
    assert "/us-east-1/bedrock/aws4_request" in authorization
    # Mantle speaks the OpenAI Responses schema, not Bedrock Converse.
    assert req["body"]["model"] == "openai.gpt-5.6-terra"
    assert "input" in req["body"]
    assert "messages" not in req["body"]


def test_mantle_model_honours_configured_region() -> None:
    req = _complete(
        {
            **_BASE,
            "region_name": "eu-west-1",
            "model": "openai.gpt-5.6-terra",
            "max_tokens": 64,
        }
    )
    assert req["url"].startswith("https://bedrock-mantle.eu-west-1.api.aws/")
    assert "/eu-west-1/bedrock/aws4_request" in req["headers"]["Authorization"]


def test_mantle_model_with_bearer_token_uses_bearer_auth() -> None:
    req = _complete(
        {
            "auth_type": "bearer_token",
            "region_name": "us-east-1",
            "aws_bearer_token": "BEDROCK_API_KEY",
            "model": "openai.gpt-5.6-terra",
            "max_tokens": 64,
        }
    )
    assert req["headers"]["Authorization"] == "Bearer BEDROCK_API_KEY"
    assert req["url"].startswith("https://bedrock-mantle.us-east-1.api.aws/")


def test_mantle_reasoning_lands_as_reasoning_effort_on_the_wire() -> None:
    """The Anthropic `thinking` block would be dropped here; effort is honoured."""
    req = _complete(
        {
            **_BASE,
            "model": "openai.gpt-5.6-terra",
            "max_tokens": 64,
            "enable_thinking": True,
        }
    )
    assert req["body"]["reasoning"]["effort"] == "medium"
    assert "thinking" not in req["body"]


def test_mantle_request_carries_no_guardrail() -> None:
    req = _complete(
        {
            **_BASE,
            "model": "openai.gpt-5.6-terra",
            "max_tokens": 64,
            "guardrail_identifier": "ff6ujrregl1q",
            "guardrail_version": "1",
        }
    )
    assert "guardrailConfig" not in req["body"]
    assert "guardrail" not in json.dumps(req["body"]).lower()


def test_claude_still_routes_to_converse_with_guardrail() -> None:
    """Control: the classic Bedrock path must be untouched by the new routing."""
    req = _complete(
        {
            **_BASE,
            "model": "anthropic.claude-3-haiku-20240307-v1:0",
            "max_tokens": 64,
            "guardrail_identifier": "ff6ujrregl1q",
            "guardrail_version": "1",
        }
    )
    assert req["url"] == (
        "https://bedrock-runtime.us-east-1.amazonaws.com/model/"
        "anthropic.claude-3-haiku-20240307-v1%3A0/converse"
    )
    assert req["body"]["guardrailConfig"]["guardrailIdentifier"] == "ff6ujrregl1q"
    # Converse schema, not OpenAI.
    assert "messages" in req["body"]


def test_mantle_cost_is_resolvable() -> None:
    """A model string LiteLLM cannot price records usage at $0 silently.

    ``audit.py`` looks cost up from the validated model string and swallows any
    exception, so an unpriced prefix is revenue-affecting but invisible.
    """
    from litellm import cost_per_token

    validated = AWSBedrockLLMParameters.validate(
        {**_BASE, "model": "openai.gpt-5.6-terra"}
    )
    prompt_cost, completion_cost = cost_per_token(
        model=validated["model"], prompt_tokens=1_000_000, completion_tokens=1_000_000
    )
    assert prompt_cost > 0
    assert completion_cost > 0
