"""Provider errors reach the user as one readable line.

The exceptions here are real litellm exceptions, raised by litellm itself
against a local HTTP server that answers with the provider's actual error
body. That pins the contract to litellm's string format — streaming wraps
the body in a bytes repr, Mistral repeats the class name — rather than to a
hand-built approximation of it.
"""

from __future__ import annotations

import json
import sys
import threading
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING
from unittest.mock import patch

import litellm
import pytest
from unstract.sdk1.exceptions import (
    LLMError,
    SdkError,
    format_provider_error,
    parse_litellm_err,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

ANTHROPIC_ADAPTER_ID = "anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203"
RETIRED_MODEL = "claude-sonnet-4-20250514"
ANTHROPIC_RETIRED_BODY = {
    "type": "error",
    "error": {"type": "not_found_error", "message": f"model: {RETIRED_MODEL}"},
    "request_id": "req_011CfbL1yvFpPPSQB81HnWmr",
}
OPENAI_NOT_FOUND_BODY = {
    "error": {
        "message": "The model `gpt-9` does not exist or you do not have access to it.",
        "type": "invalid_request_error",
        "param": None,
        "code": "model_not_found",
    }
}
_REAL_COMPLETION = litellm.completion


class _ProviderStub:
    """Local HTTP server answering every POST with one canned error."""

    def __init__(self) -> None:
        self.status = 500
        self.body: object = {}
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                self.rfile.read(int(self.headers.get("content-length", 0)))
                raw = (
                    stub.body
                    if isinstance(stub.body, bytes)
                    else json.dumps(stub.body).encode()
                )
                self.send_response(stub.status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args: object) -> None:
                pass

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def respond(self, status: int, body: object) -> None:
        self.status = status
        self.body = body

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def provider() -> Iterator[_ProviderStub]:
    stub = _ProviderStub()
    yield stub
    stub.close()


def _raise_from_litellm(provider: _ProviderStub, model: str, stream: bool) -> Exception:
    try:
        response = _REAL_COMPLETION(
            model=model,
            api_base=provider.url,
            api_key="test-key",
            messages=[{"role": "user", "content": "hi"}],
            stream=stream,
            num_retries=0,
        )
        if stream:
            for _ in response:
                pass
    except Exception as e:  # noqa: BLE001 - the exception is the subject
        return e
    pytest.fail("litellm did not raise")


@pytest.mark.parametrize("stream", [False, True], ids=["non-streaming", "streaming"])
def test_retired_anthropic_model_reads_as_model_not_found(
    provider: _ProviderStub, stream: bool
) -> None:
    provider.respond(404, ANTHROPIC_RETIRED_BODY)
    err = _raise_from_litellm(provider, f"anthropic/{RETIRED_MODEL}", stream)

    message = format_provider_error(err)

    assert message.startswith(f"NotFoundError (HTTP 404): model: {RETIRED_MODEL}")
    assert "(request_id: req_011CfbL1yvFpPPSQB81HnWmr)" in message
    assert f"Model '{RETIRED_MODEL}' was not found by the provider" in message
    assert "retired" in message
    for noise in ("b'", '{"type"', "AnthropicException", "litellm."):
        assert noise not in message


def test_plain_text_provider_message_is_kept(provider: _ProviderStub) -> None:
    provider.respond(404, OPENAI_NOT_FOUND_BODY)
    err = _raise_from_litellm(provider, "openai/gpt-9", stream=False)

    message = format_provider_error(err)

    assert message.startswith(
        "NotFoundError (HTTP 404): The model `gpt-9` does not exist"
    )
    assert "Model 'gpt-9' was not found by the provider" in message
    assert "OpenAIException" not in message


def test_repeated_class_name_is_dropped_and_no_model_hint_on_auth(
    provider: _ProviderStub,
) -> None:
    provider.respond(401, {"message": "Unauthorized", "request_id": "abc"})
    err = _raise_from_litellm(provider, "mistral/mistral-large", stream=False)

    assert format_provider_error(err) == (
        "AuthenticationError (HTTP 401): Unauthorized (request_id: abc)"
    )


def test_non_json_body_is_shown_as_is(provider: _ProviderStub) -> None:
    provider.respond(400, b"upstream exploded")
    err = _raise_from_litellm(provider, "anthropic/claude-x", stream=True)

    assert format_provider_error(err) == ("BadRequestError (HTTP 400): upstream exploded")


def test_litellm_retry_suffix_is_still_stripped() -> None:
    err = litellm.RateLimitError(
        message="AnthropicException - slow down LiteLLM Retried: 3 times",
        llm_provider="anthropic",
        model="claude-x",
    )

    assert format_provider_error(err) == "RateLimitError (HTTP 429): slow down"


def test_non_provider_errors_keep_their_text() -> None:
    assert format_provider_error(ValueError("bad metadata")) == "bad metadata"


def test_embedding_errors_use_the_same_format(provider: _ProviderStub) -> None:
    provider.respond(404, ANTHROPIC_RETIRED_BODY)
    err = _raise_from_litellm(provider, f"anthropic/{RETIRED_MODEL}", stream=True)

    wrapped = parse_litellm_err(err, "my-embedding (Anthropic)")

    assert isinstance(wrapped, SdkError)
    assert wrapped.status_code == 404
    assert wrapped.message.startswith("Error from my-embedding (Anthropic).")
    assert f"NotFoundError (HTTP 404): model: {RETIRED_MODEL}" in wrapped.message
    assert "b'" not in wrapped.message


@lru_cache(maxsize=1)
def _load_llm_module() -> object:
    sys.modules.setdefault("magic", ModuleType("magic"))
    return import_module("unstract.sdk1.llm")


def test_llm_complete_surfaces_the_readable_error(provider: _ProviderStub) -> None:
    """End to end through ``LLM.complete`` — the path API deployments hit."""
    provider.respond(404, ANTHROPIC_RETIRED_BODY)
    llm = _load_llm_module().LLM(
        adapter_id=ANTHROPIC_ADAPTER_ID,
        adapter_metadata={"model": RETIRED_MODEL, "api_key": "test-key"},
    )

    def to_stub(**kwargs: object) -> object:
        return _REAL_COMPLETION(**{**kwargs, "api_base": provider.url})

    with (
        patch.object(litellm, "completion", side_effect=to_stub),
        pytest.raises(LLMError) as exc_info,
    ):
        llm.complete("hi")

    err = exc_info.value
    assert err.status_code == 404
    assert err.message.startswith(
        "Error from LLM adapter 'anthropic': "
        f"NotFoundError (HTTP 404): model: {RETIRED_MODEL}"
    )
    assert "Update the model configured in this adapter." in err.message
    assert "b'" not in err.message
