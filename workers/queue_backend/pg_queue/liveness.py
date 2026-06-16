"""Shared tiny HTTP liveness probe for PG-queue processes.

Both the consumer (poll loop) and the reaper (tick loop) need the same probe:
"is this loop still making progress?". This is the single implementation,
parameterised by a freshness callable + the payload's ``check``/age labels (and
an optional extra-status callable — e.g. the reaper's ``is_leader``). Each side
wraps it in a thin subclass with its own constructor shape.

Deliberately lean. A *liveness* probe must answer one question — progress — and
nothing else. It must NOT depend on broker/DB reachability or resource pressure:
a transient backend blip or a busy moment would otherwise make the orchestrator
crash-loop an otherwise-healthy process. So this does not reuse the shared
``HealthChecker`` (which bundles api-connectivity / system-resource checks meant
for richer health reporting, not liveness).

Serves ``/health`` (also ``/healthz``, ``/livez``) on ``0.0.0.0`` (a
container/k8s probe reaches it from outside the process) in a daemon thread.
Bind ``port=0`` to let the OS pick a free port (read back via :attr:`bound_port`)
— used in tests. Start once; :meth:`stop` returns it to the inert state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class LivenessServer:
    """Generic liveness probe: 200 while ``freshness_fn()`` is within
    ``stale_after`` seconds, else 503.

    ``check_name`` / ``age_key`` label the JSON payload; ``extra_status_fn``
    (optional) merges extra fields in (informational — it never affects the
    200/503 verdict, which is purely the freshness heartbeat).
    """

    _PATHS = frozenset({"/health", "/healthz", "/livez"})

    def __init__(
        self,
        *,
        freshness_fn: Callable[[], float],
        stale_after: float,
        port: int,
        check_name: str,
        age_key: str,
        extra_status_fn: Callable[[], dict[str, Any]] | None = None,
        thread_name: str = "pg-queue-liveness",
    ) -> None:
        self._freshness_fn = freshness_fn
        self._stale_after = stale_after
        self._port = port
        self._check_name = check_name
        self._age_key = age_key
        self._extra_status_fn = extra_status_fn
        self._thread_name = thread_name
        self._httpd: Any = None
        self._thread: Any = None

    def start(self) -> None:
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from urllib.parse import urlsplit

        if self._httpd is not None:
            raise RuntimeError("LivenessServer already started")

        freshness_fn = self._freshness_fn
        stale_after = self._stale_after
        paths = self._PATHS
        check_name = self._check_name
        age_key = self._age_key
        extra_status_fn = self._extra_status_fn

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                # Strip any query string — a probe like /health?foo=bar must match.
                if urlsplit(self.path).path not in paths:
                    self.send_response(404)
                    self.end_headers()
                    return
                # One clock read so age and the healthy/stale verdict share an
                # instant. The verdict is purely freshness — extra_status_fn
                # fields are informational and never flip it.
                age = freshness_fn()
                stale = age > stale_after
                payload: dict[str, Any] = {
                    "status": "unhealthy" if stale else "healthy",
                    "check": check_name,
                    age_key: round(age, 3),
                    "stale_after_seconds": stale_after,
                }
                if extra_status_fn is not None:
                    payload.update(extra_status_fn())
                body = json.dumps(payload).encode()
                self.send_response(503 if stale else 200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # client (probe) hung up mid-response — not our problem

            def log_message(self, *_: object) -> None:
                pass  # silence per-request access logging

            def log_error(self, fmt: str, *args: object) -> None:
                # BaseHTTPRequestHandler routes errors through log_message too;
                # don't let the pass above swallow them — surface to our logger.
                logger.warning("pg-queue liveness handler: " + fmt, *args)

        def _serve(httpd: Any) -> None:
            try:
                httpd.serve_forever()
            except Exception:
                # A daemon thread dying silently would make /health stop
                # answering (connection refused) with no breadcrumb.
                logger.exception("pg-queue liveness server thread crashed")

        httpd = HTTPServer(("0.0.0.0", self._port), _Handler)
        self._httpd = httpd
        self._thread = threading.Thread(
            target=_serve, args=(httpd,), daemon=True, name=self._thread_name
        )
        self._thread.start()

    @property
    def bound_port(self) -> int:
        """Actual listening port (resolves ``port=0``); the requested port if not started."""
        if self._httpd is not None:
            return self._httpd.server_address[1]
        return self._port

    def stop(self) -> None:
        """Shut the server down. Defensive: never raises (called from a finally)."""
        try:
            if self._httpd is not None:
                self._httpd.shutdown()
                self._httpd.server_close()
            if self._thread is not None:
                self._thread.join(timeout=5)
                if self._thread.is_alive():
                    logger.warning("pg-queue liveness thread did not stop within 5s")
        except Exception:
            logger.exception("pg-queue: error stopping liveness server")
        finally:
            self._httpd = None
            self._thread = None
