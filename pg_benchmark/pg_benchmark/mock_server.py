"""Instant OpenAI-compatible mock server for zero-cost load testing.

Stands in for the LLM + embedding adapters during a PG-vs-Celery transport
benchmark: point an OpenAI-compatible adapter's ``api_base`` at this server and
every chat/embedding call returns a canned response in ~milliseconds — so an
execution exercises the full queue → fan-out → executor path with **no real
inference cost**, and the transport (not the LLM) becomes the measured variable.
Pair with Unstract's built-in ``noOpX2text`` + ``noOpVectorDb`` adapters for a
fully free pipeline.

Dependency-free (stdlib ``http.server``, threaded so concurrent executions don't
serialise) — runs anywhere the harness runs. NOT for production: no auth, canned
data only.

Run:  ``python -m pg_benchmark.mock_server --port 8901``
Then set the adapter ``api_base`` to ``http://<host>:8901/v1``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock


@dataclass(frozen=True, slots=True)
class MockConfig:
    """Canned-response knobs for the mock server."""

    content: str = '{"result": "mock"}'  # chat completion message content
    embedding_dim: int = 1536
    latency_ms: float = 0.0  # artificial per-request delay (0 = instant)

    @property
    def latency_s(self) -> float:
        return self.latency_ms / 1000.0


# Fixed model name returned in every response. Deliberately NOT echoed from the
# request body — never reflect untrusted client input back into the response.
MOCK_MODEL = "mock-model"


class _Counter:
    """Thread-safe request tallies (so a load run can confirm the server was hit)."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.chat = 0
        self.embeddings = 0

    def bump(self, kind: str) -> int:
        with self._lock:
            value = getattr(self, kind) + 1
            setattr(self, kind, value)
            return value


def chat_completion(model: str, content: str) -> dict:
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def text_completion(model: str, content: str) -> dict:
    return {
        "id": "cmpl-mock",
        "object": "text_completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "text": content, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def embeddings(model: str, count: int, dim: int) -> dict:
    vector = [0.0] * dim
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": vector}
            for i in range(max(1, count))
        ],
        "model": model,
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }


def _make_handler(config: MockConfig, counter: _Counter) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        # HTTP/1.1 + explicit Content-Length → keep-alive works (LiteLLM reuses
        # connections under load).
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:  # silence per-request logging
            pass

        def _send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                parsed = json.loads(raw or b"{}")
            except ValueError:
                return {}
            return parsed if isinstance(parsed, dict) else {}

        def do_GET(self) -> None:  # noqa: N802 — http.server API
            path = self.path.rstrip("/")
            if path.endswith("/models"):
                self._send_json(
                    {"object": "list", "data": [{"id": "mock-model", "object": "model"}]}
                )
            elif path.endswith("/health"):
                self._send_json(
                    {
                        "status": "ok",
                        "chat": counter.chat,
                        "embeddings": counter.embeddings,
                    }
                )
            else:
                self._send_json({"error": "not found"}, status=404)

        def do_POST(self) -> None:  # noqa: N802 — http.server API
            if config.latency_s:
                time.sleep(config.latency_s)
            req = self._read_json()
            # Always respond with MOCK_MODEL — never echo the request's "model"
            # (untrusted input) back into the response body.
            path = self.path
            # Order matters: chat/completions must be matched before the bare
            # /completions suffix.
            if path.endswith("/chat/completions"):
                counter.bump("chat")
                self._send_json(chat_completion(MOCK_MODEL, config.content))
            elif path.endswith("/embeddings"):
                counter.bump("embeddings")
                inputs = req.get("input", "")
                count = len(inputs) if isinstance(inputs, list) else 1
                self._send_json(embeddings(MOCK_MODEL, count, config.embedding_dim))
            elif path.endswith("/completions"):
                counter.bump("chat")
                self._send_json(text_completion(MOCK_MODEL, config.content))
            else:
                self._send_json({"error": "not found"}, status=404)

    return Handler


def make_server(
    config: MockConfig, host: str = "0.0.0.0", port: int = 8901
) -> tuple[ThreadingHTTPServer, _Counter]:
    """Build (but don't start) a threaded mock server. ``port=0`` picks a free port."""
    counter = _Counter()
    server = ThreadingHTTPServer((host, port), _make_handler(config, counter))
    return server, counter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pg_benchmark.mock_server",
        description="Instant OpenAI-compatible mock LLM+embedding server for load testing.",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8901)
    parser.add_argument("--embedding-dim", type=int, default=1536)
    parser.add_argument(
        "--content",
        default='{"result": "mock"}',
        help="canned chat-completion message content",
    )
    parser.add_argument(
        "--latency-ms",
        type=float,
        default=0.0,
        help="artificial per-request latency (0 = instant; use to simulate adapters)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = MockConfig(
        content=args.content,
        embedding_dim=args.embedding_dim,
        latency_ms=args.latency_ms,
    )
    server, _counter = make_server(config, host=args.host, port=args.port)
    print(
        f"mock OpenAI server on http://{args.host}:{args.port}/v1 "
        f"(chat/completions + embeddings; dim={args.embedding_dim}, "
        f"latency={args.latency_ms}ms) — Ctrl-C to stop",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping mock server", flush=True)
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
