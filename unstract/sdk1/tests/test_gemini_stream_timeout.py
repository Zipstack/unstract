"""Streamed Gemini calls honour the adapter's ``timeout``.

LiteLLM's Gemini handler (``gemini/*`` and ``vertex_ai/*gemini*``) drops the
per-call ``timeout`` on the sync streaming path and streams on
``litellm.module_level_client``, whose deadline is ``litellm.request_timeout``
(6000 s by default). In production a hung ``vertex_ai/gemini-3.1-flash-lite``
stream was therefore bounded by 100 minutes per attempt, not the adapter's
600 s (UN-4223). ``LLM`` passes its own client for these models so the
adapter's timeout reaches the HTTP request.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import import_module
from typing import TYPE_CHECKING
from unittest.mock import patch

import httpx
import litellm
import pytest
from litellm.llms.custom_httpx.http_handler import HTTPHandler
from litellm.llms.vertex_ai.vertex_llm_base import VertexBase

if TYPE_CHECKING:
    from collections.abc import Iterator

GEMINI_ADAPTER_ID = "gemini|085f6c03-b57e-4594-85bb-40e2616c2736"
VERTEX_ADAPTER_ID = "vertexai|78fa17a5-a619-47d4-ac6e-3fc1698fdb55"
_REAL_COMPLETION = litellm.completion


@lru_cache(maxsize=1)
def _load_llm_module() -> object:
    import sys
    from types import ModuleType

    sys.modules.setdefault("magic", ModuleType("magic"))
    return import_module("unstract.sdk1.llm")


@pytest.fixture
def no_cost() -> Iterator[None]:
    llm_module = _load_llm_module()
    with patch.object(llm_module.litellm, "cost_per_token", return_value=(0.0, 0.0)):
        yield


# ── Which calls get a client ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "model", ["vertex_ai/gemini-3.1-flash-lite", "gemini/gemini-2.5-flash"]
)
def test_gemini_models_get_a_client_with_the_adapter_timeout(model: str) -> None:
    llm_module = _load_llm_module()
    kwargs = {"model": model, "timeout": 600}

    result = llm_module._with_gemini_stream_timeout(kwargs)

    client = result["client"]
    assert isinstance(client, HTTPHandler)
    assert client.client.timeout.read == 600
    assert "client" not in kwargs  # the caller's kwargs are not mutated


@pytest.mark.parametrize(
    "model",
    [
        "anthropic/claude-sonnet-4-6",
        # A Vertex partner model takes LiteLLM's partner route, which forwards
        # ``timeout`` itself.
        "vertex_ai/claude-sonnet-4-6",
        "openai/gpt-4o",
    ],
)
def test_other_models_are_left_untouched(model: str) -> None:
    llm_module = _load_llm_module()
    kwargs = {"model": model, "timeout": 600}

    assert llm_module._with_gemini_stream_timeout(kwargs) is kwargs


@pytest.mark.parametrize("timeout", [None, 0])
def test_no_client_without_a_usable_timeout(timeout: object) -> None:
    llm_module = _load_llm_module()
    kwargs = {"model": "gemini/gemini-2.5-flash", "timeout": timeout}

    assert "client" not in llm_module._with_gemini_stream_timeout(kwargs)


def test_caller_supplied_client_is_kept() -> None:
    llm_module = _load_llm_module()
    own = HTTPHandler(timeout=30)
    kwargs = {"model": "gemini/gemini-2.5-flash", "timeout": 600, "client": own}

    assert llm_module._with_gemini_stream_timeout(kwargs)["client"] is own


def test_client_is_shared_per_timeout() -> None:
    llm_module = _load_llm_module()
    first = llm_module._with_gemini_stream_timeout(
        {"model": "gemini/gemini-2.5-flash", "timeout": 600}
    )
    second = llm_module._with_gemini_stream_timeout(
        {"model": "vertex_ai/gemini-2.5-pro", "timeout": 600.0}
    )

    assert first["client"] is second["client"]


# ── The timeout reaches the HTTP request ─────────────────────────────────────


def _gemini_sse_body(text: str) -> bytes:
    event = {
        "candidates": [
            {
                "content": {"parts": [{"text": text}], "role": "model"},
                "finishReason": "STOP",
                "index": 0,
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 1,
            "candidatesTokenCount": 1,
            "totalTokenCount": 2,
        },
    }
    return f"data: {json.dumps(event)}\n\n".encode()


@pytest.fixture
def sent() -> Iterator[list[httpx.Request]]:
    """Capture outgoing HTTP requests and answer each with a Gemini stream."""
    requests: list[httpx.Request] = []

    def handle_request(
        _transport: httpx.HTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_gemini_sse_body("hello"),
        )

    # Vertex needs an OAuth token; skip the Google auth round trip.
    with (
        patch.object(httpx.HTTPTransport, "handle_request", handle_request),
        patch.object(
            VertexBase, "_ensure_access_token", return_value=("token", "test-project")
        ),
    ):
        yield requests


def _gemini_llm(timeout: int) -> object:
    return _load_llm_module().LLM(
        adapter_id=GEMINI_ADAPTER_ID,
        adapter_metadata={
            "model": "gemini-2.5-flash",
            "api_key": "test-key",
            "timeout": timeout,
        },
    )


def _vertex_llm(timeout: int) -> object:
    return _load_llm_module().LLM(
        adapter_id=VERTEX_ADAPTER_ID,
        adapter_metadata={
            "model": "gemini-2.5-flash",
            "json_credentials": "{}",
            "project": "test-project",
            "timeout": timeout,
        },
    )


# Without the client LLM passes, each of these requests goes out with
# LiteLLM's 6000 s ``request_timeout`` instead of the adapter's.


def test_gemini_complete_request_carries_the_adapter_timeout(
    no_cost: None, sent: list[httpx.Request]
) -> None:
    result = _gemini_llm(timeout=420).complete("hi")

    assert result["response"].text == "hello"
    assert len(sent) == 1
    assert sent[0].extensions["timeout"]["read"] == 420


def test_vertex_complete_request_carries_the_adapter_timeout(
    no_cost: None, sent: list[httpx.Request]
) -> None:
    result = _vertex_llm(timeout=300).complete("hi")

    assert result["response"].text == "hello"
    assert len(sent) == 1
    assert "aiplatform.googleapis.com" in str(sent[0].url)
    assert sent[0].extensions["timeout"]["read"] == 300


def test_gemini_stream_complete_request_carries_the_adapter_timeout(
    no_cost: None, sent: list[httpx.Request]
) -> None:
    text = "".join(r.text for r in _gemini_llm(timeout=240).stream_complete("hi"))

    assert text == "hello"
    assert len(sent) == 1
    assert sent[0].extensions["timeout"]["read"] == 240
