"""A streamed completion releases its pooled HTTP connection (UN-4237).

Executor workers deadlocked under load inside httpcore's connection pool.
LiteLLM's sync stream wrapper has no ``close()`` and stops iterating before
the HTTP body ends, so every streamed completion left its response checked
out of the pool. The garbage collector finalised it later, and when that
happened on a thread already inside ``ConnectionPool.handle_request``, the
finaliser's ``PoolByteStream.close()`` waited on the same non-reentrant lock
the thread held: a deadlock no timeout could break.

These tests run the real litellm Anthropic path against a local server
speaking Anthropic's SSE format, with the garbage collector disabled so it
cannot be the one releasing anything. Then they reproduce the deadlock's
trigger directly: a garbage collection inside the pool lock on the next call.
"""

from __future__ import annotations

import gc
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
from typing import TYPE_CHECKING
from unittest.mock import patch

import httpcore
import litellm
import pytest
from litellm.litellm_core_utils import litellm_logging, streaming_handler
from litellm.llms.custom_httpx.http_handler import HTTPHandler

if TYPE_CHECKING:
    from collections.abc import Iterator

ANTHROPIC_ADAPTER_ID = "anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203"
TEXT = "hello over a real socket"
# Bounds how long a regressed test hangs before failing.
DEADLOCK_TIMEOUT_SECONDS = 10
_REAL_COMPLETION = litellm.completion

_EVENTS: list[tuple[str, dict[str, object]]] = [
    (
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-6",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 1},
            },
        },
    ),
    (
        "content_block_start",
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
    ),
    (
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": TEXT},
        },
    ),
    ("content_block_stop", {"type": "content_block_stop", "index": 0}),
    (
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 5},
        },
    ),
    ("message_stop", {"type": "message_stop"}),
]
# Content arrives, then Anthropic reports a mid-stream error. The connection
# is still open when litellm raises, so only an explicit close releases it. A
# dropped connection would not test this: httpcore closes those itself.
_ERROR_AFTER = 3
_ERROR_EVENT = {
    "type": "error",
    "error": {"type": "overloaded_error", "message": "Overloaded"},
}


def _sse(event: str, data: dict[str, object]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


class _AnthropicSSEHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    mid_stream_error = False

    def log_message(self, *_: object) -> None:
        pass

    def _chunk(self, body: bytes) -> None:
        self.wfile.write(b"%x\r\n%s\r\n" % (len(body), body))
        self.wfile.flush()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.rfile.read(int(self.headers.get("content-length", 0)))
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()
        for i, (event, data) in enumerate(_EVENTS):
            if self.mid_stream_error and i == _ERROR_AFTER:
                self._chunk(_sse("error", _ERROR_EVENT))
            self._chunk(_sse(event, data))
        self._chunk(b"")


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, *_: object) -> None:
        # A client closing mid-stream is the behaviour under test, not a fault.
        pass


@pytest.fixture
def server() -> Iterator[ThreadingHTTPServer]:
    handler = type("_Handler", (_AnthropicSSEHandler,), {})
    srv = _QuietServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def pools() -> Iterator[set[httpcore.ConnectionPool]]:
    """Every httpcore pool a request went through during the test."""
    seen: set[httpcore.ConnectionPool] = set()
    real = httpcore.ConnectionPool.handle_request

    def handle_request(
        pool: httpcore.ConnectionPool, request: httpcore.Request
    ) -> httpcore.Response:
        seen.add(pool)
        return real(pool, request)

    with patch.object(httpcore.ConnectionPool, "handle_request", handle_request):
        yield seen


@pytest.fixture
def client() -> HTTPHandler:
    """A pool of the test's own.

    litellm otherwise reuses one module-level client, so a stream leaked by a
    regressed test would deadlock whichever later test the collector ran in,
    hanging the suite instead of failing the test. Not closed on teardown:
    closing takes the pool lock, which a regressed deadlock test never frees.
    """
    return HTTPHandler()


class _LoggingExecutor:
    """litellm's background logging, made something a test can wait for.

    Its tasks hold the stream wrapper, so a leaked stream only becomes
    garbage once they finish.
    """

    _MODULES = (streaming_handler, litellm_logging)

    def __init__(self) -> None:
        self._originals = [module.executor for module in self._MODULES]
        self._install(ThreadPoolExecutor(max_workers=2))

    def _install(self, executor: ThreadPoolExecutor) -> None:
        self._executor = executor
        for module in self._MODULES:
            module.executor = executor

    def drain(self) -> None:
        """Wait for every task submitted so far, then accept new ones."""
        self._executor.shutdown(wait=True)
        self._install(ThreadPoolExecutor(max_workers=2))

    def restore(self) -> None:
        self._executor.shutdown(wait=False)
        for module, original in zip(self._MODULES, self._originals, strict=True):
            module.executor = original


@pytest.fixture
def logging_executor() -> Iterator[_LoggingExecutor]:
    executor = _LoggingExecutor()
    try:
        yield executor
    finally:
        executor.restore()


@pytest.fixture
def no_gc() -> Iterator[None]:
    """Keep the garbage collector from releasing what the code should."""
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()


@lru_cache(maxsize=1)
def _load_llm_module() -> object:
    import sys
    from types import ModuleType

    sys.modules.setdefault("magic", ModuleType("magic"))
    return import_module("unstract.sdk1.llm")


def _checked_out(pools: set[httpcore.ConnectionPool]) -> int:
    """Requests whose response the pool still considers open."""
    return sum(len(pool._requests) for pool in pools)


def _complete(srv: ThreadingHTTPServer, client: HTTPHandler) -> dict[str, object]:
    """Run ``LLM.complete()`` for Anthropic against the local server."""
    llm_module = _load_llm_module()
    llm = llm_module.LLM(
        adapter_id=ANTHROPIC_ADAPTER_ID,
        adapter_metadata={"model": "claude-sonnet-4-6", "api_key": "test-key"},
    )
    api_base = f"http://127.0.0.1:{srv.server_port}"

    def completion(**kwargs: object) -> object:
        return _REAL_COMPLETION(**kwargs, api_base=api_base, client=client)

    with (
        patch.object(llm_module.litellm, "completion", completion),
        patch.object(llm_module.litellm, "cost_per_token", return_value=(0.0, 0.0)),
    ):
        return llm.complete("hi", max_retries=0)


def test_completed_stream_releases_its_connection(
    server: ThreadingHTTPServer,
    client: HTTPHandler,
    pools: set[httpcore.ConnectionPool],
    no_gc: None,
) -> None:
    result = _complete(server, client)

    assert result["response"].text == TEXT
    assert pools, "the request never reached httpcore"
    assert _checked_out(pools) == 0


def test_stream_failing_after_content_releases_its_connection(
    server: ThreadingHTTPServer,
    client: HTTPHandler,
    pools: set[httpcore.ConnectionPool],
    no_gc: None,
) -> None:
    server.RequestHandlerClass.mid_stream_error = True
    llm_module = _load_llm_module()

    with pytest.raises(llm_module.LLMError):
        _complete(server, client)

    assert pools, "the request never reached httpcore"
    assert _checked_out(pools) == 0


def test_gc_inside_the_pool_lock_does_not_deadlock(
    server: ThreadingHTTPServer,
    client: HTTPHandler,
    logging_executor: _LoggingExecutor,
    no_gc: None,
) -> None:
    """The production deadlock, triggered on purpose.

    Under load the collector ran on an allocation inside ``handle_request``'s
    locked section. Forcing a collection there, after a completed stream, is
    what deadlocked every time before the fix. Takes no ``pools`` fixture:
    pytest reprs a failing test's arguments, and ``ConnectionPool.__repr__``
    takes the very lock a regressed run leaves held.
    """
    _complete(server, client)
    # Until litellm's logging tasks finish they still reference the first
    # stream, and a collection would find nothing to finalise.
    logging_executor.drain()

    real_assign = httpcore.ConnectionPool._assign_requests_to_connections

    def assign(pool: httpcore.ConnectionPool) -> object:
        gc.collect()  # runs under ``pool._optional_thread_lock``
        return real_assign(pool)

    outcome: list[object] = []

    def second_call() -> None:
        try:
            outcome.append(_complete(server, client)["response"].text)
        except Exception as e:  # surfaced by the assertion below
            outcome.append(e)

    with patch.object(httpcore.ConnectionPool, "_assign_requests_to_connections", assign):
        # Daemon: if this regresses, the stuck thread must not block exit.
        worker = threading.Thread(target=second_call, daemon=True)
        worker.start()
        worker.join(DEADLOCK_TIMEOUT_SECONDS)

    assert not worker.is_alive(), "deadlocked on httpcore's pool lock"
    assert outcome == [TEXT]
