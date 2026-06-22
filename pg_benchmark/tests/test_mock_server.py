"""Unit tests for the mock OpenAI server — real HTTP on an ephemeral port."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
import requests

from pg_benchmark.mock_server import MockConfig, make_server


@pytest.fixture
def server() -> Iterator[tuple[str, object]]:
    config = MockConfig(content='{"x": 1}', embedding_dim=8, latency_ms=0)
    srv, counter = make_server(config, host="127.0.0.1", port=0)  # 0 = free port
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", counter
    finally:
        srv.shutdown()
        srv.server_close()


def test_chat_completion_shape(server):
    base, counter = server
    resp = requests.post(
        f"{base}/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        timeout=5,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == '{"x": 1}'
    assert body["choices"][0]["finish_reason"] == "stop"
    assert counter.chat == 1


def test_embeddings_batch_returns_one_vector_per_input(server):
    base, _ = server
    resp = requests.post(
        f"{base}/v1/embeddings",
        json={"model": "m", "input": ["a", "b", "c"]},
        timeout=5,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    assert len(body["data"]) == 3
    assert len(body["data"][0]["embedding"]) == 8  # configured dim


def test_embeddings_single_string_input(server):
    base, _ = server
    resp = requests.post(
        f"{base}/v1/embeddings", json={"model": "m", "input": "solo"}, timeout=5
    )
    assert len(resp.json()["data"]) == 1


def test_path_without_v1_prefix_still_matches(server):
    # LiteLLM may call /chat/completions directly if api_base already has no /v1.
    base, _ = server
    resp = requests.post(
        f"{base}/chat/completions", json={"model": "m", "messages": []}, timeout=5
    )
    assert resp.status_code == 200
    assert resp.json()["object"] == "chat.completion"


def test_health_and_models(server):
    base, _ = server
    assert requests.get(f"{base}/health", timeout=5).json()["status"] == "ok"
    models = requests.get(f"{base}/v1/models", timeout=5).json()
    assert models["data"][0]["id"] == "mock-model"


def test_unknown_path_404(server):
    base, _ = server
    assert requests.post(f"{base}/v1/nonsense", json={}, timeout=5).status_code == 404
