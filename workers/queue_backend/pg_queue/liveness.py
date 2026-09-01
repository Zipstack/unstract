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

import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from http.server import HTTPServer
    from threading import Thread

logger = logging.getLogger(__name__)


class LivenessServer:
    """Generic liveness probe: 200 while ``freshness_fn()`` is within
    ``stale_after`` seconds, else 503.

    ``check_name`` / ``age_key`` label the JSON payload; ``extra_status_fn``
    (optional) merges extra fields in (informational — it never affects the
    200/503 verdict, which is purely the freshness heartbeat).

    ``metrics_fn`` (optional) additionally serves ``/metrics``: it returns the
    Prometheus text-exposition body (bytes). Kept as an opaque callable so this
    module stays free of the prometheus dependency; the metric definitions live
    in :mod:`queue_backend.pg_queue.metrics`. A ``metrics_fn`` failure returns
    500 on ``/metrics`` only — it can never affect the ``/health`` verdict.
    """

    _PATHS = frozenset({"/health", "/healthz", "/livez"})
    _METRICS_PATH = "/metrics"
    # Prometheus text exposition format (metrics.METRICS_CONTENT_TYPE — inlined
    # so this module keeps zero imports from the metrics side).
    _METRICS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

    def __init__(
        self,
        *,
        freshness_fn: Callable[[], float],
        stale_after: float,
        port: int,
        check_name: str,
        age_key: str,
        extra_status_fn: Callable[[], dict[str, Any]] | None = None,
        metrics_fn: Callable[[], bytes] | None = None,
        thread_name: str = "pg-queue-liveness",
        log_label: str = "pg-queue",
    ) -> None:
        # Re-validate here (not only at the env boundary): a direct caller could
        # otherwise build an always-503 probe that crash-loops the pod. Mirrors
        # the codebase's load-bearing re-validation convention (PgReaper.__init__).
        if stale_after <= 0:
            raise ValueError(f"stale_after must be positive, got {stale_after!r}")
        self._freshness_fn = freshness_fn
        self._stale_after = stale_after
        self._port = port
        self._check_name = check_name
        self._age_key = age_key
        self._extra_status_fn = extra_status_fn
        self._metrics_fn = metrics_fn
        self._thread_name = thread_name
        # Prefixes the (now-shared) log messages so they stay attributable to the
        # source process after the consumer/reaper extraction (e.g. "pg-queue
        # consumer" / "pg-queue reaper") — they all log via this module's logger.
        self._log_label = log_label
        self._httpd: HTTPServer | None = None
        self._thread: Thread | None = None

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
        metrics_path = self._METRICS_PATH
        metrics_content_type = self._METRICS_CONTENT_TYPE
        metrics_fn = self._metrics_fn
        check_name = self._check_name
        age_key = self._age_key
        extra_status_fn = self._extra_status_fn
        log_label = self._log_label

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                # Strip any query string — a probe like /health?foo=bar must match.
                path = urlsplit(self.path).path
                if metrics_fn is not None and path == metrics_path:
                    self._serve_metrics()
                    return
                if path not in paths:
                    self.send_response(404)
                    self.end_headers()
                    return
                # One clock read so age and the healthy/stale verdict share an
                # instant. The verdict is purely freshness — extra_status_fn
                # fields are informational and never flip it.
                age = freshness_fn()
                stale = age > stale_after
                # Extra fields first, then overlay the core fields — so a caller's
                # extra_status_fn can NEVER clobber status/check/age_key/
                # stale_after_seconds (which a monitor reads): core always wins.
                payload: dict[str, Any] = {}
                if extra_status_fn is not None:
                    payload.update(extra_status_fn())
                payload.update(
                    {
                        "status": "unhealthy" if stale else "healthy",
                        "check": check_name,
                        age_key: round(age, 3),
                        "stale_after_seconds": stale_after,
                    }
                )
                body = json.dumps(payload).encode()
                # Headers too, not just the body write: a client that hangs up
                # before headers go out would otherwise raise into socketserver's
                # handle_error, which prints an unattributed traceback to stderr.
                try:
                    self.send_response(503 if stale else 200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # client (probe) hung up mid-response — not our problem

            def _serve_metrics(self) -> None:
                # A broken metrics renderer must degrade to a 500 on /metrics
                # alone — the probe verdict on /health stays untouched.
                try:
                    body = metrics_fn()  # type: ignore[misc]  # guarded by caller
                except Exception:
                    logger.exception("%s: /metrics render failed", log_label)
                    with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                        self.send_response(500)
                        self.end_headers()
                    return
                # Same hung-up-client guard as the /health path above.
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", metrics_content_type)
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # scraper hung up mid-response — not our problem

            def log_message(self, *_: object) -> None:
                pass  # silence per-request access logging

            def log_error(self, fmt: str, *args: object) -> None:
                # BaseHTTPRequestHandler routes errors through log_message too;
                # don't let the pass above swallow them — surface to our logger.
                logger.warning(f"{log_label} liveness handler: " + fmt, *args)

        def _serve(httpd: HTTPServer) -> None:
            try:
                httpd.serve_forever()
            except Exception:
                # A daemon thread dying silently would make /health stop
                # answering (connection refused) with no breadcrumb.
                logger.exception("%s liveness server thread crashed", log_label)

        httpd = HTTPServer(("0.0.0.0", self._port), _Handler)
        self._httpd = httpd
        self._thread = threading.Thread(
            target=_serve, args=(httpd,), daemon=True, name=self._thread_name
        )
        self._thread.start()

    @property
    def bound_port(self) -> int:
        """Actual listening port once started (resolves ``port=0`` to the
        OS-chosen port). Before :meth:`start` / after :meth:`stop`, returns the
        configured port value (which is ``0`` when the OS is asked to choose).
        """
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
                    logger.warning(
                        "%s liveness thread did not stop within 5s", self._log_label
                    )
        except Exception:
            logger.exception("%s: error stopping liveness server", self._log_label)
        finally:
            self._httpd = None
            self._thread = None
